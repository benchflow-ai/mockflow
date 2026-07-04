"""Database seeder — creates users and documents for each scenario."""

from __future__ import annotations

import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from faker import Faker

from mock_gdoc.models import (
    reset_engine,
    init_db,
    get_session_factory,
    User,
    Document,
    DocumentRevision,
    Comment,
    Reply,
    Permission,
)
from mock_gdoc.state.snapshots import take_snapshot
from mock_gdoc.seed.body_builder import text_to_body, extract_plain_text
from mock_gdoc.seed.content import USER_EMAIL, USER_NAME, ALL_DOCUMENTS, PERSONAS
from mock_gdoc.seed.filler import generate_filler_documents

# Target document count for the long_context scenario: the full handwritten
# library plus generated filler up to this total (search/pagination stress test).
LONG_CONTEXT_TARGET_DOCS = 3000


def seed_database(
    scenario: str = "default",
    seed: int = 42,
    db_path: str | Path | None = None,
    num_users: int = 1,
    task_data_path: str | Path | None = None,
    task_name: str | None = None,
) -> dict:
    """Seed database with a scenario. Return stats."""
    random.seed(seed)
    Faker.seed(seed)
    fake = Faker()

    reset_engine()
    init_db(db_path)
    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        # Create primary user
        user = User(
            id="user_0",
            email=USER_EMAIL,
            display_name=USER_NAME,
        )
        db.add(user)
        db.flush()

        # Create all persona users (collaborators for sharing/comments)
        persona_users = {}
        next_uid = 1
        for key, persona in PERSONAS.items():
            if persona["email"] == USER_EMAIL:
                persona_users[key] = user
                continue
            uid = f"user_{next_uid}"
            next_uid += 1
            u = User(
                id=uid,
                email=persona["email"],
                display_name=persona["name"],
            )
            db.add(u)
            persona_users[key] = u
        db.flush()

        if task_data_path:
            stats = _seed_task_scenario(
                db,
                fake,
                user,
                scenario=f"task:{task_name or Path(task_data_path).parent.name}",
                task_data_path=task_data_path,
            )
        elif scenario == "default":
            stats = _seed_default(db, fake, user, persona_users)
        elif scenario == "long_context":
            stats = _seed_long_context(db, fake, user, persona_users)
        elif scenario.startswith("task:"):
            stats = _seed_task_scenario(db, fake, user, scenario)
        else:
            raise ValueError(f"Unknown scenario: {scenario!r}")

        db.commit()
        take_snapshot("initial")

        return stats
    finally:
        db.close()


def _seed_default(db, fake: Faker, user: User, persona_users: dict) -> dict:
    """Seed the 16 handwritten library documents with comments and permissions."""
    now = datetime.now(timezone.utc)
    doc_count = 0
    doc_ids = []

    for doc_data in ALL_DOCUMENTS:
        doc_count += 1
        doc_id = _create_document_from_data(db, user, doc_data, now)
        doc_ids.append((doc_id, doc_data))

    # Seed some permissions and comments on a subset of documents
    comment_count = 0
    perm_count = 0
    collaborators = [u for key, u in persona_users.items() if u.id != user.id]

    for idx, (doc_id, doc_data) in enumerate(doc_ids):
        # Share ~30% of docs with 1-2 collaborators
        if idx % 3 == 0 and collaborators:
            num_collabs = min(random.randint(1, 2), len(collaborators))
            chosen = random.sample(collaborators, num_collabs)
            for collab in chosen:
                role = random.choice(["writer", "commenter", "reader"])
                perm = Permission(
                    id=f"perm_{uuid.uuid4().hex[:12]}",
                    document_id=doc_id,
                    type="user",
                    role=role,
                    email_address=collab.email,
                    user_id=collab.id,
                    display_name=collab.display_name,
                    created_time=now - timedelta(days=random.randint(1, 14)),
                )
                db.add(perm)
                perm_count += 1

        # Add ~20% of docs have 1-3 comment threads
        if idx % 5 == 0 and collaborators:
            # Extract sentences from document for quoted_text
            plain = extract_plain_text(
                db.query(Document).filter(Document.id == doc_id).first().body
            )
            sentences = _extract_sentences(plain)

            num_comments = random.randint(1, 3)
            for _ in range(num_comments):
                author = random.choice([user] + collaborators[:3])
                quoted = random.choice(sentences) if sentences and random.random() < 0.7 else None
                thread = random.choice(_SEED_THREADS) if random.random() < 0.5 else None
                comment_content = thread["comment"] if thread else random.choice(_SEED_COMMENTS)
                comment_created = now - timedelta(days=random.randint(2, 10))
                comment_id = f"comment_{uuid.uuid4().hex[:12]}"
                is_resolved = random.random() < 0.3
                comment = Comment(
                    id=comment_id,
                    document_id=doc_id,
                    author_id=author.id,
                    content=comment_content,
                    resolved=is_resolved,
                    quoted_text=quoted,
                    created_time=comment_created,
                    modified_time=comment_created + timedelta(hours=random.randint(0, 12)),
                )
                db.add(comment)
                comment_count += 1

                # Add replies to threads
                if thread and thread.get("replies"):
                    reply_pool = [u for u in [user] + collaborators[:3] if u.id != author.id]
                    for ri, reply_text in enumerate(thread["replies"]):
                        reply_author = random.choice(reply_pool) if reply_pool else author
                        reply_created = comment_created + timedelta(hours=random.randint(1, 48) + ri * 2)
                        if reply_created > now:
                            reply_created = now - timedelta(minutes=random.randint(5, 60))
                        db.add(Reply(
                            id=f"reply_{uuid.uuid4().hex[:12]}",
                            comment_id=comment_id,
                            author_id=reply_author.id,
                            content=reply_text,
                            created_time=reply_created,
                            modified_time=reply_created,
                        ))

    total_users = len(persona_users)
    return {"users": total_users, "documents": doc_count, "comments": comment_count, "permissions": perm_count}


def _seed_long_context(
    db,
    fake: Faker,
    user: User,
    persona_users: dict,
    target_count: int = LONG_CONTEXT_TARGET_DOCS,
) -> dict:
    """Seed ``target_count`` documents for search/pagination stress testing.

    The full handwritten library is seeded first, then generated filler
    documents (realistic standups, specs, postmortems, etc.) fill the rest up
    to ``target_count``. No comments or permissions are seeded — this scenario
    focuses on document volume.
    """
    now = datetime.now(timezone.utc)
    doc_count = 0

    # Include all handwritten content first.
    for doc_data in ALL_DOCUMENTS:
        doc_count += 1
        _create_document_from_data(db, user, doc_data, now)

    # Fill the remainder with generated filler documents.
    remaining = max(0, target_count - doc_count)
    for filler in generate_filler_documents(remaining, random, fake):
        _create_document(
            db, user,
            title=filler["title"],
            body_text=filler["body"],
            days_ago=filler["days_ago"],
            now=now,
        )
        doc_count += 1

    total_users = len(persona_users)
    return {"users": total_users, "documents": doc_count}


def _seed_task_scenario(
    db,
    fake: Faker,
    user: User,
    scenario: str,
    task_data_path: str | Path | None = None,
) -> dict:
    """Seed a task-specific scenario by loading needles.py from the task directory."""
    task_name = scenario.removeprefix("task:")
    now = datetime.now(timezone.utc)
    doc_count = 0

    def candidate_task_roots() -> list[Path]:
        roots: list[Path] = []
        for env_name in ("TASKS_DIR", "ENV0_TASKS_DIR"):
            env_value = os.environ.get(env_name)
            if env_value:
                roots.append(Path(env_value))
        for parent in Path(__file__).resolve().parents:
            roots.append(parent / "example_tasks")
            roots.append(parent / "tasks")
        unique: list[Path] = []
        seen: set[Path] = set()
        for root in roots:
            resolved = root.expanduser()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(resolved)
        return unique

    # Find needles.py
    if task_data_path:
        needles_path = Path(task_data_path) / "needles.py"
    else:
        needles_path = next(
            (
                root / task_name / "data" / "needles.py"
                for root in candidate_task_roots()
                if (root / task_name / "data" / "needles.py").exists()
            ),
            candidate_task_roots()[0] / task_name / "data" / "needles.py",
        )

    if not needles_path.exists():
        raise ValueError(f"needles.py not found for task {task_name!r} at {needles_path}")

    # Load needles module
    import importlib.util
    module_name = f"gdoc_needles_{task_name.replace('-', '_')}_{abs(hash(str(needles_path.resolve())))}"
    spec = importlib.util.spec_from_file_location(module_name, needles_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    needles = getattr(module, "NEEDLES", [])
    normal_files = getattr(module, "NORMAL_FILES", [])

    for nd in needles:
        _create_document(
            db, user,
            title=nd.get("name", "Untitled"),
            body_text=nd.get("content_text", ""),
            days_ago=nd.get("days_ago", 7),
            now=now,
            doc_id=nd.get("id"),
        )
        doc_count += 1
    for nf in normal_files:
        _create_document(
            db, user,
            title=nf.get("name", "Untitled"),
            body_text=nf.get("content_text", ""),
            days_ago=nf.get("days_ago", 7),
            now=now,
            doc_id=nf.get("id"),
        )
        doc_count += 1

    return {"users": 1, "documents": doc_count}


def _create_document_from_data(db, user: User, doc_data: dict, now: datetime) -> str:
    """Create a document from content library data. Returns the doc ID."""
    owner = doc_data.get("owner", "{user}")
    if owner == "{user}":
        owner_id = user.id
    else:
        owner_id = user.id  # All docs belong to the primary user for now

    days_ago = doc_data.get("days_ago", 7)
    return _create_document(
        db, user,
        title=doc_data["title"],
        body_text=doc_data["body"],
        days_ago=days_ago,
        now=now,
    )


def _create_document(
    db, user: User,
    title: str,
    body_text: str,
    days_ago: int,
    now: datetime,
    doc_id: str | None = None,
) -> str:
    """Create a single document with revision. Returns the doc ID."""
    if doc_id is None:
        doc_id = str(uuid.uuid4()).replace("-", "")[:44]
    rev_id = str(uuid.uuid4()).replace("-", "")[:8]
    created = now - timedelta(days=days_ago)
    modified = created + timedelta(hours=random.randint(0, 48))
    if modified > now:
        modified = now

    doc = Document(
        id=doc_id,
        title=title,
        revision_id=rev_id,
        user_id=user.id,
        created_time=created,
        modified_time=modified,
    )
    doc.body = text_to_body(body_text)
    db.add(doc)

    db.add(DocumentRevision(
        id=f"rev_{rev_id}",
        document_id=doc_id,
        user_id=user.id,
        modified_time=modified,
    ))
    return doc_id



def seed_from_gdrive(
    gdrive_db_path: str | Path,
    db_path: str | Path | None = None,
) -> dict:
    """Seed gdoc database by mirroring files from a gdrive database.

    Reads all users and non-folder files from gdrive.db, creates matching
    Documents in gdoc.db with body_json derived via text_to_body().
    """
    import sqlite3

    FOLDER_MIME = "application/vnd.google-apps.folder"

    # Connect to gdrive DB (read-only)
    gdrive_conn = sqlite3.connect(f"file:{gdrive_db_path}?mode=ro", uri=True)
    gdrive_conn.row_factory = sqlite3.Row

    # Init gdoc DB
    reset_engine()
    init_db(db_path)
    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        # Mirror users
        gdrive_users = gdrive_conn.execute("SELECT id, email, display_name FROM users").fetchall()
        user_map = {}
        for u in gdrive_users:
            user = User(
                id=u["id"],
                email=u["email"],
                display_name=u["display_name"],
            )
            db.add(user)
            user_map[u["id"]] = user
        db.flush()

        # Mirror non-folder files as Documents
        files = gdrive_conn.execute(
            "SELECT id, name, content_text, owner_id, created_time, modified_time "
            "FROM files WHERE mime_type != ?",
            (FOLDER_MIME,),
        ).fetchall()

        doc_count = 0
        for f in files:
            rev_id = str(uuid.uuid4()).replace("-", "")[:8]

            created_time = None
            modified_time = None
            if f["created_time"]:
                try:
                    created_time = datetime.fromisoformat(f["created_time"])
                except (ValueError, TypeError):
                    pass
            if f["modified_time"]:
                try:
                    modified_time = datetime.fromisoformat(f["modified_time"])
                except (ValueError, TypeError):
                    pass

            owner_id = f["owner_id"] if f["owner_id"] in user_map else list(user_map.keys())[0]

            doc = Document(
                id=f["id"],
                title=f["name"],
                revision_id=rev_id,
                user_id=owner_id,
                created_time=created_time or datetime.now(timezone.utc),
                modified_time=modified_time or datetime.now(timezone.utc),
            )
            doc.body = text_to_body(f["content_text"] or "")
            db.add(doc)

            db.add(DocumentRevision(
                id=f"rev_{rev_id}",
                document_id=f["id"],
                user_id=owner_id,
                modified_time=modified_time or datetime.now(timezone.utc),
            ))
            doc_count += 1

        db.commit()
        take_snapshot("initial")

        return {
            "users": len(gdrive_users),
            "documents": doc_count,
            "source": str(gdrive_db_path),
        }
    finally:
        db.close()
        gdrive_conn.close()


def _extract_sentences(text: str) -> list[str]:
    """Extract short phrase-like snippets from document text for quoted_text."""
    import re
    parts = re.split(r'[.!?\n]', text)
    sentences = []
    for p in parts:
        p = p.strip()
        if 10 < len(p) < 120 and not p.startswith(("-", "[", "#")):
            sentences.append(p)
    return sentences


# Standalone comments (no thread)
_SEED_COMMENTS = [
    "Can we revisit this section? I think there are some inaccuracies.",
    "LGTM! Nice work on this.",
    "Should we add more detail here?",
    "I have some concerns about the timeline mentioned.",
    "+1, this aligns with what we discussed last week.",
    "This needs to be updated with the latest numbers.",
    "Typo: should be 'their' not 'there'.",
    "We need sign-off from legal on this paragraph.",
    "Could you add a reference link here?",
]


# Comment threads with realistic back-and-forth replies
_SEED_THREADS = [
    {
        "comment": "This contradicts what we agreed on in the sprint planning. Can someone double-check?",
        "replies": [
            "Good catch — I'll verify against the sprint notes and update by EOD.",
            "Updated. Let me know if this looks right now.",
        ],
    },
    {
        "comment": "Can you clarify what you mean by this? The wording is a bit ambiguous.",
        "replies": [
            "Sure — I meant that we'd run the migration in parallel, not sequentially. I'll rephrase.",
        ],
    },
    {
        "comment": "I think we should move this to a separate document. It's getting long.",
        "replies": [
            "Agreed — I can split it out after the review. Want me to create the new doc now?",
            "Go ahead, and link it back here so we don't lose the context.",
        ],
    },
    {
        "comment": "Let's discuss this in the next meeting. I don't think we have enough data to decide now.",
        "replies": [
            "Added it to the agenda for Thursday's sync.",
        ],
    },
    {
        "comment": "Great summary! This is really helpful for onboarding new team members.",
        "replies": [
            "Thanks! I'll keep it updated as things change.",
            "Could we pin this in the team channel too?",
        ],
    },
    {
        "comment": "The numbers here don't match the dashboard. Can you re-pull from Looker?",
        "replies": [
            "Oops, these were from last month's export. Updating now.",
            "Done — should match the live dashboard as of today.",
        ],
    },
    {
        "comment": "Is this still accurate? I thought we changed the policy last quarter.",
        "replies": [
            "You're right, the policy was updated in January. Let me fix this.",
        ],
    },
    {
        "comment": "@Sarah — can you review the budget estimates in this section?",
        "replies": [
            "Looking at it now. The Q2 projections seem optimistic — I'd add a 15% buffer.",
            "Good point. Updated with the buffer. Thanks!",
        ],
    },
]
