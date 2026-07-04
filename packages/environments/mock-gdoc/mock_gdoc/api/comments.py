"""Comments API endpoints — Google Drive-style comments on documents."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from mock_gdoc.models import Comment, Reply, User
from .deps import (
    get_db,
    resolve_user_id,
    check_document_access,
    check_comment_permission,
)
from .schemas import (
    CommentSchema,
    CommentCreateRequest,
    CommentUpdateRequest,
    CommentListResponse,
    ReplySchema,
    ReplyCreateRequest,
)

router = APIRouter()


def _reply_to_schema(reply: Reply) -> dict:
    author = reply.author
    return ReplySchema(
        id=reply.id,
        author={
            "displayName": author.display_name if author else "Unknown",
            "emailAddress": author.email if author else "",
        },
        content=reply.content,
        createdTime=reply.created_time.isoformat() if reply.created_time else None,
        modifiedTime=reply.modified_time.isoformat() if reply.modified_time else None,
    ).model_dump(exclude_none=True)


def _comment_to_schema(comment: Comment) -> dict:
    author = comment.author
    replies = [_reply_to_schema(r) for r in comment.replies]
    return CommentSchema(
        id=comment.id,
        documentId=comment.document_id,
        content=comment.content,
        author={
            "displayName": author.display_name if author else "Unknown",
            "emailAddress": author.email if author else "",
        },
        resolved=comment.resolved,
        quotedText=comment.quoted_text,
        replies=replies,
        createdTime=comment.created_time.isoformat() if comment.created_time else None,
        modifiedTime=comment.modified_time.isoformat() if comment.modified_time else None,
    ).model_dump(exclude_none=True)


def _comment_load_options():
    """Standard joinedload options for loading a comment with author and replies."""
    return [
        joinedload(Comment.author),
        joinedload(Comment.replies).joinedload(Reply.author),
    ]


def _load_comment(db: Session, document_id: str, comment_id: str) -> Comment:
    """Load a comment with its author and replies eagerly loaded."""
    comment = (
        db.query(Comment)
        .options(*_comment_load_options())
        .filter(Comment.id == comment_id, Comment.document_id == document_id)
        .first()
    )
    if not comment:
        raise HTTPException(404, f"Comment '{comment_id}' not found")
    return comment


@router.get("/documents/{documentId}/comments", tags=["comments"])
def list_comments(
    documentId: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """List all comments on a document."""
    check_document_access(db, documentId, user_id)
    # Legacy Query has no .unique(); entity rows are deduped from joinedload
    # collections when .all() materializes the results.
    comments = (
        db.query(Comment)
        .options(*_comment_load_options())
        .filter(Comment.document_id == documentId)
        .order_by(Comment.created_time.asc())
        .all()
    )
    return CommentListResponse(
        comments=[_comment_to_schema(c) for c in comments],
        count=len(comments),
    )


@router.post("/documents/{documentId}/comments", tags=["comments"])
def create_comment(
    documentId: str,
    request: CommentCreateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Create a comment on a document."""
    check_comment_permission(db, documentId, user_id)
    comment_id = f"comment_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    comment = Comment(
        id=comment_id,
        document_id=documentId,
        author_id=user_id,
        content=request.content,
        quoted_text=request.quotedText,
        created_time=now,
        modified_time=now,
    )
    db.add(comment)
    db.commit()
    comment = _load_comment(db, documentId, comment_id)
    return _comment_to_schema(comment)


@router.get("/documents/{documentId}/comments/{commentId}", tags=["comments"])
def get_comment(
    documentId: str,
    commentId: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Get a single comment."""
    check_document_access(db, documentId, user_id)
    comment = _load_comment(db, documentId, commentId)
    return _comment_to_schema(comment)


@router.patch("/documents/{documentId}/comments/{commentId}", tags=["comments"])
def update_comment(
    documentId: str,
    commentId: str,
    request: CommentUpdateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Update a comment (only the author can update)."""
    check_comment_permission(db, documentId, user_id)
    comment = _load_comment(db, documentId, commentId)
    if comment.author_id != user_id:
        raise HTTPException(403, "Only the comment author can edit this comment")
    if request.content is not None:
        comment.content = request.content
    if request.quotedText is not None:
        comment.quoted_text = request.quotedText
    comment.modified_time = datetime.now(timezone.utc)
    db.commit()
    comment = _load_comment(db, documentId, commentId)
    return _comment_to_schema(comment)


@router.delete("/documents/{documentId}/comments/{commentId}", tags=["comments"])
def delete_comment(
    documentId: str,
    commentId: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Delete a comment (author or document owner)."""
    doc = check_document_access(db, documentId, user_id)
    comment = _load_comment(db, documentId, commentId)
    if comment.author_id != user_id and doc.user_id != user_id:
        raise HTTPException(403, "Only the comment author or document owner can delete this comment")
    result = _comment_to_schema(comment)
    db.delete(comment)
    db.commit()
    return result


@router.post("/documents/{documentId}/comments/{commentId}/resolve", tags=["comments"])
def resolve_comment(
    documentId: str,
    commentId: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Resolve a comment."""
    check_comment_permission(db, documentId, user_id)
    comment = _load_comment(db, documentId, commentId)
    comment.resolved = True
    comment.modified_time = datetime.now(timezone.utc)
    db.commit()
    comment = _load_comment(db, documentId, commentId)
    return _comment_to_schema(comment)


@router.post("/documents/{documentId}/comments/{commentId}/reopen", tags=["comments"])
def reopen_comment(
    documentId: str,
    commentId: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Reopen a resolved comment."""
    check_comment_permission(db, documentId, user_id)
    comment = _load_comment(db, documentId, commentId)
    comment.resolved = False
    comment.modified_time = datetime.now(timezone.utc)
    db.commit()
    comment = _load_comment(db, documentId, commentId)
    return _comment_to_schema(comment)


# --- Reply endpoints ---

@router.post("/documents/{documentId}/comments/{commentId}/replies", tags=["comments"])
def create_reply(
    documentId: str,
    commentId: str,
    request: ReplyCreateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Add a reply to a comment."""
    check_comment_permission(db, documentId, user_id)
    _load_comment(db, documentId, commentId)
    reply_id = f"reply_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    reply = Reply(
        id=reply_id,
        comment_id=commentId,
        author_id=user_id,
        content=request.content,
        created_time=now,
        modified_time=now,
    )
    db.add(reply)
    db.commit()
    comment = _load_comment(db, documentId, commentId)
    return _comment_to_schema(comment)


@router.delete("/documents/{documentId}/comments/{commentId}/replies/{replyId}", tags=["comments"])
def delete_reply(
    documentId: str,
    commentId: str,
    replyId: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Delete a reply (author or document owner)."""
    doc = check_document_access(db, documentId, user_id)
    _load_comment(db, documentId, commentId)
    reply = db.query(Reply).filter(Reply.id == replyId, Reply.comment_id == commentId).first()
    if not reply:
        raise HTTPException(404, f"Reply '{replyId}' not found")
    if reply.author_id != user_id and doc.user_id != user_id:
        raise HTTPException(403, "Only the reply author or document owner can delete this reply")
    db.delete(reply)
    db.commit()
    comment = _load_comment(db, documentId, commentId)
    return _comment_to_schema(comment)
