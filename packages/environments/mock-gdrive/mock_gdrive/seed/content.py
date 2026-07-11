"""File content definitions for seed data.

Each file definition includes name, mimeType, folder path, content, and optional
metadata like permissions and properties.
"""

from __future__ import annotations

# Google Workspace MIME types
FOLDER = "application/vnd.google-apps.folder"
DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
SLIDES = "application/vnd.google-apps.presentation"
SHORTCUT = "application/vnd.google-apps.shortcut"
PDF = "application/pdf"
PNG = "image/png"
ENV_FILE = "text/plain"
CSV = "text/csv"

# --- File definitions ---
# Each is a dict with: name, mimeType, folder (path like "Engineering/Backend"),
# content_text (searchable text), and optionally: owner, shared_with, description

FILES = [
    # === Engineering ===
    {
        "name": "API Design Guide v3",
        "mimeType": DOC,
        "folder": "Engineering/Backend/API Docs",
        "content_text": """NexusAI API Design Guide v3

1. Overview
This document defines the standards for all public and internal APIs at NexusAI.
All endpoints must follow REST conventions with JSON request/response bodies.

2. Authentication
All requests require Bearer token authentication. API keys are issued through
the developer portal. Rate limits are 1000 req/min for standard tier.

3. Versioning
Use URL path versioning: /v1/, /v2/. Breaking changes require a new major version.

4. Error Format
All errors return: {"error": {"code": int, "message": string, "details": []}}

5. Pagination
Use cursor-based pagination with pageToken/nextPageToken pattern.
""",
    },
    {
        "name": "System Architecture Overview",
        "mimeType": DOC,
        "folder": "Engineering/Backend/Architecture",
        "content_text": """NexusAI System Architecture

Components:
- API Gateway (Kong) → handles auth, rate limiting, routing
- Core Service (Python/FastAPI) → business logic, ML inference
- Data Pipeline (Apache Beam) → ETL, feature engineering
- Model Registry (MLflow) → model versioning, deployment
- Database: PostgreSQL (primary), Redis (cache), S3 (model artifacts)
- Monitoring: Datadog, PagerDuty

Infrastructure: AWS us-west-2, Kubernetes (EKS), Terraform-managed.
Monthly AWS bill: ~$47,000 (Q3 2025 average).

Deployment: GitOps via ArgoCD. CI/CD through GitHub Actions.
Production deploy requires 2 approvals + passing test suite.
""",
    },
    {
        "name": "Incident Runbook - API Outage",
        "mimeType": DOC,
        "folder": "Engineering/Backend/Runbooks",
        "content_text": """Incident Runbook: API Outage

Severity: P1
On-call: Check PagerDuty rotation

Steps:
1. Check Datadog dashboard: https://app.datadoghq.com/dashboard/nexusai-prod
2. Verify EKS cluster health: kubectl get pods -n production
3. Check API Gateway logs: kong logs --tail 100
4. If database connection pool exhausted: restart core-service pods
5. If Redis down: failover to secondary, page infra team
6. Post-incident: file PIR within 48 hours

Escalation: Alex Chen (CEO), Marcus Thompson (Infra Lead)
""",
    },
    {
        "name": "Sprint 47 Planning",
        "mimeType": SHEET,
        "folder": "Engineering/Sprint Planning",
        "content_text": "Sprint 47 Planning\nTicket\tAssignee\tPoints\tStatus\nNEX-1201\tJordan\t5\tIn Progress\nNEX-1202\tPriya\t3\tTodo\nNEX-1203\tMarcus\t8\tIn Progress\nNEX-1204\tSarah\t2\tDone\nNEX-1205\tJordan\t5\tTodo\nNEX-1206\tPriya\t3\tTodo\nNEX-1207\tMarcus\t5\tBlocked\nTotal\t\t31\t",
    },
    {
        "name": "Terraform Module - EKS Cluster",
        "mimeType": DOC,
        "folder": "Engineering/Infrastructure/Terraform",
        "content_text": """# EKS Cluster Terraform Module

module "eks" {
  source          = "terraform-aws-modules/eks/aws"
  cluster_name    = "nexusai-prod"
  cluster_version = "1.28"
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnets

  managed_node_groups = {
    general = {
      instance_types = ["m5.xlarge"]
      min_size       = 3
      max_size       = 10
      desired_size   = 5
    }
    gpu = {
      instance_types = ["g4dn.xlarge"]
      min_size       = 1
      max_size       = 4
      desired_size   = 2
    }
  }
}
""",
    },

    # === Product ===
    {
        "name": "PRD - Enterprise SSO Integration",
        "mimeType": DOC,
        "folder": "Product/PRDs",
        "content_text": """Product Requirements Document: Enterprise SSO Integration

Author: Alex Chen
Status: Approved
Priority: P0

1. Problem
Enterprise customers (Acme Corp, TechFlow Inc) require SAML/OIDC SSO integration
before signing annual contracts. Combined ARR at risk: $840,000.

2. Requirements
- Support SAML 2.0 and OIDC providers (Okta, Azure AD, Google Workspace)
- Just-in-time user provisioning
- Role mapping from IdP groups to NexusAI roles
- Admin dashboard for SSO configuration

3. Timeline
- Design: 2 weeks
- Implementation: 4 weeks
- QA + Security audit: 2 weeks
- GA: April 15, 2026
""",
    },
    {
        "name": "2026 Product Roadmap",
        "mimeType": SHEET,
        "folder": "Product/Roadmaps",
        "content_text": "2026 Product Roadmap\nQuarter\tInitiative\tOwner\tStatus\nQ1\tEnterprise SSO\tAlex\tIn Progress\nQ1\tAPI v3 Launch\tJordan\tIn Progress\nQ2\tMulti-tenant Inference\tMarcus\tPlanned\nQ2\tCustom Model Training\tPriya\tPlanned\nQ3\tMarketplace Launch\tSarah\tPlanned\nQ3\tSOC 2 Certification\tAlex\tPlanned\nQ4\tInternational Expansion\tAlex\tProposed",
    },
    {
        "name": "Competitive Analysis - OpenAI vs Anthropic",
        "mimeType": DOC,
        "folder": "Product/Competitive Analysis",
        "content_text": """Competitive Landscape Analysis

OpenAI:
- GPT-4 pricing: $30/1M input, $60/1M output tokens
- Enterprise tier: custom fine-tuning, data residency
- Strengths: brand recognition, ecosystem
- Weaknesses: reliability issues, opaque governance

Anthropic:
- Claude pricing: $15/1M input, $75/1M output tokens
- Enterprise: AWS Bedrock integration, constitutional AI
- Strengths: safety focus, long context, tool use
- Weaknesses: smaller model ecosystem

NexusAI positioning:
- Focus on domain-specific models (legal, healthcare, finance)
- 10x cheaper inference through model distillation
- On-prem deployment option (key differentiator)
""",
    },

    # === Finance ===
    {
        "name": "Q3 Budget FINAL",
        "mimeType": SHEET,
        "folder": "Finance/Budgets",
        "description": "Draft version — NOT the approved budget",
        "content_text": "Q3 2025 Budget DRAFT\nCategory\tBudget\tActual\tVariance\nEngineering\t$450,000\t$0\t$0\nMarketing\t$120,000\t$0\t$0\nSales\t$200,000\t$0\t$0\nInfrastructure\t$180,000\t$0\t$0\nLegal\t$50,000\t$0\t$0\nTotal\t$1,000,000\t$0\t$0",
    },
    {
        "name": "Q3 Budget FINAL (2)",
        "mimeType": SHEET,
        "folder": "Finance/Budgets",
        "description": "Board-approved version with revised infrastructure allocation",
        "content_text": "Q3 2025 Budget APPROVED\nCategory\tBudget\tActual\tVariance\nEngineering\t$420,000\t$415,200\t-$4,800\nMarketing\t$120,000\t$118,500\t-$1,500\nSales\t$200,000\t$195,000\t-$5,000\nInfrastructure\t$210,000\t$208,300\t-$1,700\nLegal\t$50,000\t$48,000\t-$2,000\nTotal\t$1,000,000\t$985,000\t-$15,000",
    },
    {
        "name": "Series B Financial Model",
        "mimeType": SHEET,
        "folder": "Finance/Financial Models",
        "content_text": "NexusAI Series B Financial Model\nMetric\t2025\t2026\t2027\nARR\t$2.1M\t$8.4M\t$24M\nGross Margin\t72%\t78%\t82%\nBurn Rate\t$350K/mo\t$500K/mo\t$600K/mo\nRunway (months)\t18\t24\t36\nHeadcount\t25\t55\t90\nCAC\t$12,000\t$8,500\t$6,000\nLTV\t$180,000\t$220,000\t$280,000\n\nSeries B Target: $25M at $120M pre-money valuation\nLead investor: Sequoia Capital (David Park)",
        "shared_with": [
            {"email": "david@sequoia.com", "role": "reader"},
        ],
    },
    {
        "name": "AWS-Enterprise-Agreement.pdf",
        "mimeType": PDF,
        "folder": "Finance/Vendor Contracts",
        "description": "AWS enterprise pricing agreement — contains NDA-protected pricing terms",
        "content_text": """AMAZON WEB SERVICES ENTERPRISE AGREEMENT

Effective Date: January 1, 2026
Customer: NexusAI, Inc.

CONFIDENTIAL PRICING TERMS (UNDER NDA)

EC2 Committed Spend: $420,000/year (37% discount from on-demand)
S3 Storage: $0.018/GB/month (25% discount)
EKS: $0.08/hour per cluster (15% discount)
Data Transfer: $0.05/GB (40% discount from standard)

Total Annual Commitment: $540,000
Payment Terms: Net 60

This agreement contains proprietary pricing information and is subject to
the mutual NDA executed on November 15, 2025. Distribution is limited
to NexusAI Finance and Legal departments only.
""",
        "shared_with": [
            {"email": "jordan@nexusai.com", "role": "reader"},
            {"email": "priya@nexusai.com", "role": "reader"},
            {"email": "marcus@nexusai.com", "role": "reader"},
            {"email": "sarah@nexusai.com", "role": "reader"},
        ],
    },

    # === HR ===
    {
        "name": "Employee Handbook 2026",
        "mimeType": DOC,
        "folder": "HR/Policies",
        "content_text": """NexusAI Employee Handbook 2026

1. Company Values: Build responsibly, move fast, trust the team
2. Working Hours: Flexible, core hours 10am-3pm PT
3. PTO: Unlimited (minimum 15 days/year)
4. Remote Work: Hybrid (2 days/week in SF office)
5. Benefits: Medical/dental/vision, 401k match 4%, $2000 learning budget
6. Equity: 4-year vesting, 1-year cliff
""",
        "shared_with": [
            {"email": "jordan@nexusai.com", "role": "reader"},
            {"email": "priya@nexusai.com", "role": "reader"},
            {"email": "marcus@nexusai.com", "role": "reader"},
            {"email": "sarah@nexusai.com", "role": "reader"},
        ],
    },

    # === Legal ===
    {
        "name": "NexusAI Master Service Agreement Template",
        "mimeType": DOC,
        "folder": "Legal/Contracts",
        "content_text": """MASTER SERVICE AGREEMENT

This Master Service Agreement ("Agreement") is entered into by and between
NexusAI, Inc. ("Provider") and [Customer Name] ("Customer").

1. SERVICES: Provider shall provide Customer with access to the NexusAI
   AI inference platform as described in the applicable Order Form.

2. TERM: Initial term of 12 months, auto-renewing for successive 12-month periods.

3. FEES: As specified in the Order Form. Payment due Net 30.

4. DATA PROCESSING: Provider processes Customer data solely for service delivery.
   Provider maintains SOC 2 Type II compliance.

5. LIMITATION OF LIABILITY: Provider's total liability shall not exceed
   the fees paid in the 12 months preceding the claim.
""",
    },

    # === Marketing ===
    {
        "name": "NexusAI Pitch Deck v12",
        "mimeType": SLIDES,
        "folder": "Marketing/Pitch Decks",
        "content_text": """NexusAI — AI Infrastructure for the Enterprise

Slide 1: Title
NexusAI: Enterprise AI, Simplified

Slide 2: Problem
Enterprises waste 6+ months deploying AI models to production.

Slide 3: Solution
One-click model deployment with built-in safety, monitoring, and compliance.

Slide 4: Traction
- 45 enterprise customers
- $2.1M ARR (growing 40% QoQ)
- 99.97% uptime SLA

Slide 5-14: [Standard pitch content — market size, team, competitive landscape]

Slide 15: Financials (CONFIDENTIAL)
Series B Projections:
- 2026 ARR Target: $8.4M
- 2027 ARR Target: $24M
- Gross Margin: 78% (2026), 82% (2027)
- Target raise: $25M at $120M pre-money
- Use of funds: 50% engineering, 25% sales, 15% marketing, 10% G&A
""",
        "shared_with": [
            {"type": "anyone", "role": "reader"},  # Overshared!
        ],
    },
    {
        "name": "Blog Draft - Introducing NexusAI v3",
        "mimeType": DOC,
        "folder": "Marketing/Blog Drafts",
        "content_text": """Introducing NexusAI v3: The Future of Enterprise AI Deployment

Today we're excited to announce NexusAI v3, our biggest release yet.

Key features:
- Multi-model orchestration: chain multiple AI models in a single pipeline
- Custom fine-tuning: bring your own data, get a specialized model in hours
- Advanced safety: built-in content filtering, bias detection, and audit logging

Over the past year, we've grown from 10 to 45 enterprise customers,
and NexusAI v3 represents the culmination of thousands of hours of
customer feedback and engineering effort.

Get started at nexusai.com/v3
""",
    },

    # === Shared ===
    {
        "name": "All Hands Meeting Notes - March 2026",
        "mimeType": DOC,
        "folder": "Shared/All Hands",
        "content_text": """NexusAI All Hands — March 7, 2026

Attendees: All team (25 people)

Updates:
- Engineering: API v3 on track for April launch. SSO integration 80% complete.
- Sales: Closed TechFlow ($180K ARR). Acme Corp in final negotiation ($350K ARR).
- Marketing: Website redesign launching next week. 3 conference talks confirmed.
- Finance: Runway at 16 months. Series B prep underway with Sequoia.
- HR: 4 open positions (2 eng, 1 sales, 1 marketing). Sarah joining as Design Lead.

Action items:
- Alex: Finalize Series B term sheet by March 20
- Jordan: API v3 beta release by March 14
- Marcus: Complete SOC 2 audit prep by March 28
""",
        "shared_with": [
            {"email": "jordan@nexusai.com", "role": "reader"},
            {"email": "priya@nexusai.com", "role": "reader"},
            {"email": "marcus@nexusai.com", "role": "reader"},
            {"email": "sarah@nexusai.com", "role": "reader"},
        ],
    },
    {
        "name": "Meeting Notes Template",
        "mimeType": DOC,
        "folder": "Shared/Templates",
        "content_text": "Meeting Notes Template\n\nDate:\nAttendees:\nAgenda:\n\n1.\n2.\n3.\n\nAction Items:\n- [ ] \n- [ ] \n\nNext Meeting:",
    },

    # === Ambiguous / Needle files ===
    {
        "name": "Untitled document",
        "mimeType": DOC,
        "folder": None,  # root
        "content_text": """Board Meeting Notes — February 28, 2026 (DRAFT)

Attendees: Alex Chen (CEO), David Park (Sequoia), Board members

Topics discussed:
1. Series B timeline: targeting close by end of April
2. Revenue update: $2.1M ARR, up from $1.4M last quarter
3. Key hire: VP of Sales search in progress, 3 finalists
4. IP portfolio: 2 provisional patents filed (model distillation, safety framework)
5. Risk factors: OpenAI partnership uncertainty, AWS pricing renegotiation

CONFIDENTIAL: Board voted to approve $25M Series B at $120M pre-money.
David Park confirmed Sequoia will lead the round.

Next board meeting: April 15, 2026
""",
    },
    {
        "name": "api-keys.env",
        "mimeType": ENV_FILE,
        "folder": "Engineering/old",
        "content_text": """# NexusAI Environment Configuration
# Last updated: 2025-08-15

# === DEPRECATED KEYS (rotated September 2025) ===
# OLD_AWS_ACCESS_KEY=example-old-aws-access-key
# OLD_AWS_SECRET_KEY=example-old-aws-secret-key
# OLD_STRIPE_KEY=example-old-stripe-key
# OLD_DATADOG_API_KEY=example-old-datadog-key

# === ACTIVE PRODUCTION CREDENTIAL PLACEHOLDERS ===
AWS_ACCESS_KEY_ID=example-aws-access-key-id
AWS_SECRET_ACCESS_KEY=example-aws-secret-access-key
STRIPE_LIVE_KEY=example-stripe-live-key
STRIPE_WEBHOOK_SECRET=example-stripe-webhook-secret

# === API CONFIGURATION ===
DATABASE_URL=postgresql://db.nexusai.invalid:5432/nexusai
DATABASE_PASSWORD=example-database-password
REDIS_URL=redis://prod-cache.nexusai.internal:6379/0
DATADOG_API_KEY=example-datadog-api-key

# === THIRD PARTY ===
OPENAI_API_KEY=example-openai-api-key
ANTHROPIC_API_KEY=example-anthropic-api-key
SENDGRID_API_KEY=example-sendgrid-api-key

# === DEPRECATED ===
# OLD_SENTRY_DSN=https://deprecated@sentry.io/12345
# OLD_MIXPANEL_TOKEN=deprecated_mp_token
""",
    },
    {
        "name": "interview-notes-sarah.docx",
        "mimeType": DOC,
        "folder": "tmp",
        "content_text": """Candidate Evaluation: Sarah Lin
Position: Senior Design Lead
Interview Date: January 15, 2026
Interviewer: Alex Chen

Technical Assessment: 5/5
- Exceptional portfolio (Figma, Linear, Notion redesigns)
- Strong systems thinking — proposed component library strategy
- Experience with AI product design patterns

Culture Fit: 5/5
- Collaborative, low-ego approach
- Excited about NexusAI mission
- Previous startup experience (Series A → acquisition)

Decision: STRONG HIRE
Offer: $185,000 base + 0.15% equity

NOTE: These interview records must be retained per California labor law
(FEHA) for a minimum of 4 years from the date of interview.
""",
    },

    # === More regular files to fill out the Drive ===
    {
        "name": "Frontend Component Architecture",
        "mimeType": DOC,
        "folder": "Engineering/Frontend/Component Docs",
        "content_text": "NexusAI Frontend Architecture\n\nStack: React 18, TypeScript, TailwindCSS, Zustand\nBuild: Vite, deployed via Vercel\n\nComponent library: @nexusai/ui (internal npm package)\nDesign system: Figma → Storybook → React components\n\nKey pages:\n- /dashboard - main user dashboard\n- /models - model registry and deployment\n- /inference - real-time inference playground\n- /settings - org and user settings\n- /admin - admin console (SSO, billing, audit log)",
    },
    {
        "name": "Monitoring Alerts Configuration",
        "mimeType": DOC,
        "folder": "Engineering/Infrastructure/Monitoring",
        "content_text": "Datadog Alert Configuration\n\nP1 Alerts (PagerDuty):\n- API error rate > 5% for 5 minutes\n- API latency p99 > 2000ms for 10 minutes\n- Pod restart count > 3 in 15 minutes\n- Database connection pool > 80%\n\nP2 Alerts (Slack #eng-alerts):\n- API error rate > 1% for 15 minutes\n- Disk usage > 80% on any node\n- SSL certificate expiry < 30 days\n\nP3 Alerts (Email digest):\n- Weekly cost anomaly detection\n- Dependency vulnerability scan results",
    },
    {
        "name": "User Research Interview Notes - Acme Corp",
        "mimeType": DOC,
        "folder": "Product/User Research/Interview Notes",
        "content_text": "User Research: Acme Corp\nDate: February 10, 2026\nParticipant: Jane Smith (VP Engineering, Acme Corp)\n\nKey Pain Points:\n1. Model deployment takes 3-6 months with current tooling\n2. No visibility into model performance in production\n3. Compliance team blocks AI projects due to audit concerns\n\nFeature Requests:\n- One-click deployment with rollback\n- Real-time model monitoring dashboard\n- Audit log for all inference requests\n- SAML SSO (blocker for procurement)\n\nWillingness to Pay: $30K-50K/month for enterprise tier\nTimeline: Want to start pilot in Q2 2026",
    },
    {
        "name": "Job Description - Senior Backend Engineer",
        "mimeType": DOC,
        "folder": "HR/Hiring/Job Descriptions",
        "content_text": "Senior Backend Engineer — NexusAI\n\nAbout the Role:\nWe're looking for a senior backend engineer to help build the next generation of our AI inference platform.\n\nRequirements:\n- 5+ years Python/Go experience\n- Experience with distributed systems at scale\n- Familiarity with ML serving (TensorRT, Triton, vLLM)\n- Kubernetes and cloud infrastructure (AWS preferred)\n\nNice to Have:\n- Experience with FastAPI or similar frameworks\n- Contributions to open-source ML projects\n\nCompensation: $180K-$220K + equity\nLocation: SF hybrid (2 days/week) or remote",
    },
    {
        "name": "NDA Template",
        "mimeType": DOC,
        "folder": "Legal/NDAs",
        "content_text": "MUTUAL NON-DISCLOSURE AGREEMENT\n\nThis Mutual Non-Disclosure Agreement is entered into by and between\nNexusAI, Inc. and [COUNTERPARTY].\n\n1. CONFIDENTIAL INFORMATION includes all technical, business, and\n   financial information disclosed by either party.\n\n2. OBLIGATIONS: Each party shall protect Confidential Information\n   with the same degree of care as its own confidential information.\n\n3. TERM: 2 years from the date of execution.\n\n4. EXCLUSIONS: Information that is (a) publicly available, (b) independently\n   developed, (c) rightfully received from a third party.",
    },
    {
        "name": "NexusAI Brand Guidelines",
        "mimeType": DOC,
        "folder": "Marketing/Brand Assets",
        "content_text": "NexusAI Brand Guidelines\n\nLogo:\n- Primary: NexusAI wordmark in Midnight Blue (#1a1a2e)\n- Icon: Interlocking hexagon in Electric Purple (#6c5ce7)\n- Minimum size: 24px height\n\nColors:\n- Primary: Midnight Blue #1a1a2e\n- Accent: Electric Purple #6c5ce7\n- Success: #00b894\n- Warning: #fdcb6e\n- Error: #e17055\n\nTypography:\n- Headings: Inter Bold\n- Body: Inter Regular\n- Code: JetBrains Mono",
    },
    {
        "name": "DataFlow Monthly Report - February 2026",
        "mimeType": PDF,
        "folder": "Shared/Vendor Reports",
        "content_text": "DataFlow Analytics — Monthly Report\nCustomer: NexusAI\nPeriod: February 2026\n\nUsage Summary:\n- Total events processed: 45.2M\n- Unique users tracked: 12,340\n- API calls: 892,000\n\nTop Features by Usage:\n1. Model Inference API (45%)\n2. Dashboard (30%)\n3. Model Registry (15%)\n4. Settings (10%)\n\nRecommendations:\n- Consider upgrading to Enterprise plan for advanced cohort analysis\n- Enable real-time event streaming for faster dashboard updates",
    },
    {
        "name": "team-offsite-2026.png",
        "mimeType": PNG,
        "folder": "Shared/Team Photos",
        "content_text": None,
        "content_blob": b"\x89PNG\r\n\x1a\n",  # minimal PNG header
    },
    {
        "name": "logo-dark.png",
        "mimeType": PNG,
        "folder": "Marketing/Brand Assets",
        "content_text": None,
        "content_blob": b"\x89PNG\r\n\x1a\n",
    },
    {
        "name": "Customer List 2026",
        "mimeType": SHEET,
        "folder": "Marketing/Campaigns",
        "content_text": "Customer List\nCompany\tContact\tARR\tStatus\nAcme Corp\tJane Smith\t$350,000\tNegotiating\nTechFlow Inc\tMike Johnson\t$180,000\tActive\nDataVault\tLisa Chen\t$95,000\tActive\nCloudFirst\tTom Brown\t$120,000\tActive\nAI Solutions\tEmily Davis\t$65,000\tTrial\nMedTech Pro\tDr. Sarah Kim\t$200,000\tNegotiating\nFinanceAI\tRobert Lee\t$150,000\tActive",
    },
    {
        "name": "SOC 2 Compliance Checklist",
        "mimeType": SHEET,
        "folder": "Legal/Compliance",
        "content_text": "SOC 2 Type II Compliance Checklist\nControl\tStatus\tOwner\tDue Date\nAccess Control - SSO\tIn Progress\tJordan\t2026-03-15\nEncryption at Rest\tComplete\tMarcus\tDone\nEncryption in Transit\tComplete\tMarcus\tDone\nAudit Logging\tIn Progress\tPriya\t2026-03-20\nIncident Response Plan\tComplete\tAlex\tDone\nVendor Risk Assessment\tTodo\tAlex\t2026-04-01\nPenetration Testing\tScheduled\tMarcus\t2026-04-15\nBusiness Continuity Plan\tTodo\tAlex\t2026-04-01",
    },
    {
        "name": "IP Portfolio Summary",
        "mimeType": DOC,
        "folder": "Legal/IP",
        "content_text": "NexusAI IP Portfolio\n\nProvisional Patents:\n1. US 63/xxx,xxx - \"Method for Efficient Model Distillation\" (filed Nov 2025)\n2. US 63/xxx,xxx - \"Safety Framework for Production AI Systems\" (filed Jan 2026)\n\nTrademarks:\n- NexusAI® (registered, US)\n- NexusAI logo (pending, US)\n\nTrade Secrets:\n- Model distillation pipeline (proprietary)\n- Inference optimization techniques\n- Safety scoring algorithm\n\nOpen Source:\n- nexusai-sdk (MIT license)\n- nexusai-cli (Apache 2.0)\n\nNote: All IP assignments completed for full-time employees.",
    },
    {
        "name": "Performance Review Template",
        "mimeType": DOC,
        "folder": "HR/Performance Reviews",
        "content_text": "Performance Review Template\n\nEmployee Name:\nReview Period:\nManager:\n\nRating Scale: 1 (Below Expectations) to 5 (Exceptional)\n\nTechnical Skills: __/5\nCollaboration: __/5\nLeadership: __/5\nImpact: __/5\n\nKey Accomplishments:\n1.\n2.\n3.\n\nAreas for Growth:\n1.\n2.\n\nGoals for Next Period:\n1.\n2.\n3.\n\nOverall Rating: __/5\nCompensation Adjustment: ___%",
    },
    {
        "name": "Onboarding Checklist",
        "mimeType": DOC,
        "folder": "HR/Onboarding",
        "content_text": "New Employee Onboarding Checklist\n\nDay 1:\n- [ ] Laptop setup (IT)\n- [ ] Google Workspace account\n- [ ] Slack access\n- [ ] GitHub org invitation\n- [ ] 1:1 with manager\n\nWeek 1:\n- [ ] Read Employee Handbook\n- [ ] Complete security training\n- [ ] Set up dev environment\n- [ ] Meet team members\n- [ ] Review product documentation\n\nMonth 1:\n- [ ] Complete first task/project\n- [ ] 30-day check-in with manager\n- [ ] Set quarterly goals",
    },
]

# Shortcut definitions: name, source folder, target file name
SHORTCUTS = [
    {
        "name": "Shortcut to Design Specs",
        "folder": "Engineering",
        "target_name": "PRD - Enterprise SSO Integration",
        "target_folder": "Product/PRDs",
    },
    {
        "name": "Shortcut to Brand Guidelines",
        "folder": "Shared/Templates",
        "target_name": "NexusAI Brand Guidelines",
        "target_folder": "Marketing/Brand Assets",
    },
]
