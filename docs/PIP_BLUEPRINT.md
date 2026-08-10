# PIP 2.0 Architecture Blueprint

## 1. Project Purpose

PIP 2.0 is the Procurement Intelligence Platform.

The platform is intended to provide procurement data management, supplier and product price history, purchasing analysis, reporting, and intelligence.

The system must be independent from Odoo.

Odoo is a source of procurement data, not the application database.

The primary application database must be PostgreSQL.

---

## 2. Core Architecture

PIP 2.0 will be implemented as a layered architecture with the following logical layers:

1. PostgreSQL Database
   - The canonical application runtime database.
   - Stores all application-owned data required for master data, transactions, import state, and future analytics outputs.

2. SQLAlchemy ORM
   - Provides the application object model for database interaction.
   - Encapsulates persistence behavior and keeps database access consistent.

3. Alembic migrations
   - Manages explicit, versioned schema evolution.
   - Ensures the database schema changes are controlled and reviewable.

4. Master Data layer
   - Owns reference and master entities such as company, branch, warehouse, supplier, category, unit, and product.
   - Provides durable definitions for business entities used across the platform.

5. Transaction layer
   - Owns procurement transaction data imported from external sources.
   - Maintains the transactional contract without prematurely forcing a fully normalized model.

6. Odoo Import Engine
   - Handles ingestion of external procurement data from Odoo-sourced inputs.
   - Operates as a dedicated service responsible for parsing, validating, previewing, and persisting imported data.

7. Procurement Intelligence / Analytics layer
   - Supports future price intelligence, spend analysis, purchasing trend analysis, and supplier performance analysis.
   - Must remain separate from transaction persistence concerns.

8. REST API
   - Exposes application capabilities to clients.
   - Must remain thin and delegate business logic to services.

9. Dashboard / BI layer
   - Presents curated business views for users such as Supply Chain Managers.
   - Consumes analytics-oriented data and reporting concepts.

Business logic must not be duplicated across layers. Each capability must have a single authoritative implementation path.

---

## 3. Database Principle

PostgreSQL is mandatory.

The canonical application connection string is:

postgresql+psycopg2://postgres:postgres@db:5432/pip_db

SQLite must not be used by the production or application runtime.

The architecture must not silently fall back to SQLite.

Testing strategy may use isolated test databases only when explicitly designed for testing. Production configuration must remain PostgreSQL.

---

## 4. Master Data

The initial master-data domain consists of the following entities:

- Company
- Branch
- Warehouse
- Supplier
- Category
- Unit
- Product

### Approved decisions

#### Company
- Company name is not unique.
- No unique constraint will be invented for company name.

#### Supplier
- Supplier code is required.
- No additional uniqueness rules will be invented unless explicitly approved later.

#### Warehouse
- Warehouse belongs to Company.
- Warehouse must have an explicit relationship to Company.

#### Product
- Product name alone is insufficient.
- Product requires an additional identifier or code.
- No Product/Supplier, Product/Category, or Product/Unit relationships will be introduced yet.

#### Unit
- Unit is an independent master entity.
- The model must remain minimal.
- No conversion table or conversion logic will be introduced yet.

#### Branch
- Branch is a master-data entity.
- No Company relationship will be invented unless explicitly approved later.

#### Category
- Category is a minimal master-data entity.
- No additional hierarchy or relationships will be invented.

---

## 5. Transaction Domain

The transaction domain will contain Odoo procurement transaction data.

### OdooTransaction concept

OdooTransaction is a conceptual transaction record representing imported procurement transactions from Odoo-sourced data.

Important architectural rule:
- The first implementation must not force OdooTransaction into a fully normalized structure.
- The initial implementation must preserve the raw transactional import contract.
- Normalization of transaction references into foreign keys is a future controlled phase.

Transaction identity and duplicate prevention must be explicitly defined before implementation.

---

## 6. Odoo Import

Odoo Import is a separate application service.

### Import pipeline

Excel input
→ File validation
→ Header validation
→ Row parsing
→ Data normalization
→ Validation
→ Preview
→ Explicit commit
→ Transaction persistence

### Important rules

- Preview must be non-persistent.
- Commit must be explicit.
- Invalid rows must be reported clearly.
- Duplicate transactions must be detected.
- Import failures must not leave partial transaction data.
- Import logic must remain independent from API transport logic.

---

## 7. Import Architecture

The import system must separate the following responsibilities:

- File/parser layer
  - Reads and parses source files.
- Validation layer
  - Validates file structure, headers, and row content.
- Mapping layer
  - Maps parsed data into the internal import representation.
- Preview layer
  - Produces a preview of what would be imported without persisting data.
- Persistence layer
  - Persists accepted data only after explicit commit.
- Error reporting
  - Returns clear, actionable errors for invalid rows and failed imports.

The API should call the import service.

The import service must not depend directly on HTTP or FastAPI concepts.

---

## 8. Price Intelligence

PIP must eventually support:

- Supplier price history
- Product price history
- Price changes over time
- Supplier comparisons
- Quantity versus price analysis
- Purchase trends
- Current price
- Previous price
- Price variance
- Spend analysis
- Supplier performance

These capabilities are target-state requirements only. They will not be implemented as part of this initial blueprint phase.

---

## 9. Analytics

The future analytics layer should support:

- Monthly purchasing spend
- Year-to-date spend
- Supplier spend
- Category spend
- Product purchasing trends
- Price trends
- Supplier performance
- Warehouse purchasing activity
- Purchase volume analysis

Analytics must be separated from transaction persistence.

---

## 10. API

The future REST API will expose application capabilities.

The initial Odoo import API is expected to eventually provide:

- POST /api/import/odoo/preview
- POST /api/import/odoo/commit

These endpoints are not to be implemented now.

API routes should remain thin and delegate business logic to services.

---

## 11. Dashboard

The future dashboard should support a Supply Chain Manager view.

Initial KPI concepts:

- Total purchases this month
- Total purchases YTD
- Purchase trend
- Supplier spend
- Price movement
- Top purchased products
- Supplier performance

The dashboard will not be implemented in this task.

---

## 12. Project Implementation Phases

Implementation will proceed in the following order. Each phase must be completed before the next begins.

### PHASE 0 — Blueprint
- Objective: Define the architecture, scope, principles, and implementation roadmap.
- Expected deliverables:
  - Authoritative architecture blueprint document
  - Scope boundaries and implementation guardrails
- Dependencies: None.
- Validation criteria:
  - Blueprint is reviewed and accepted.
  - It clearly defines architecture, phases, and rules.

### PHASE 1 — Project Foundation
- Objective: Establish the repository structure and baseline engineering conventions.
- Expected deliverables:
  - Basic project layout
  - Documentation and contribution conventions
- Dependencies: Phase 0.
- Validation criteria:
  - Repository is consistent and ready for implementation work.
  - No conflicting architecture decisions are introduced.

### PHASE 2 — PostgreSQL + Docker
- Objective: Establish PostgreSQL as the runtime database environment.
- Expected deliverables:
  - PostgreSQL runtime configuration
  - Containerized database environment if used
- Dependencies: Phase 1.
- Validation criteria:
  - PostgreSQL is the canonical runtime database.
  - No SQLite runtime path is introduced.

### PHASE 3 — SQLAlchemy Foundation
- Objective: Establish the application persistence foundation.
- Expected deliverables:
  - SQLAlchemy configuration
  - Session and engine setup conventions
- Dependencies: Phase 2.
- Validation criteria:
  - A single SQLAlchemy metadata strategy is defined.
  - No duplicate Base or session modules are created.

### PHASE 4 — Master Data
- Objective: Implement the initial master-data entities and rules.
- Expected deliverables:
  - Company, branch, warehouse, supplier, category, unit, and product domain definitions
  - Approved constraints and relationships as documented
- Dependencies: Phase 3.
- Validation criteria:
  - Master-data entities follow the approved decisions.
  - No unapproved business rules are introduced.

### PHASE 5 — Alembic Initial Schema
- Objective: Create the initial database schema through Alembic.
- Expected deliverables:
  - Initial migration set
  - Versioned schema history
- Dependencies: Phase 4.
- Validation criteria:
  - Migration history is explicit and version controlled.
  - Alembic uses the application’s single SQLAlchemy metadata.

### PHASE 6 — Transaction Model
- Objective: Introduce the transaction-domain model for imported procurement data.
- Expected deliverables:
  - Transaction entity representation
  - Explicit identity and duplicate-prevention strategy
- Dependencies: Phase 5.
- Validation criteria:
  - The model preserves the transactional import contract.
  - Duplicate detection rules are documented and implemented deliberately.

### PHASE 7 — Odoo Import Engine
- Objective: Implement the import workflow for Odoo procurement data.
- Expected deliverables:
  - File parsing and validation pipeline
  - Preview and explicit commit flow
  - Clear error reporting and duplicate detection
- Dependencies: Phase 6.
- Validation criteria:
  - Preview is non-persistent.
  - Commit is explicit.
  - Failed imports do not leave partial transaction data.

### PHASE 8 — Import API
- Objective: Expose import capabilities through the REST API.
- Expected deliverables:
  - Thin API routes for preview and commit operations
  - Delegation to the import service layer
- Dependencies: Phase 7.
- Validation criteria:
  - API routes remain thin.
  - Import business logic is not embedded in transport code.

### PHASE 9 — Price Intelligence
- Objective: Add price-history and price-analysis capabilities.
- Expected deliverables:
  - Supplier and product price history features
  - Price change and comparison analysis
- Dependencies: Phase 8.
- Validation criteria:
  - Analytics logic is implemented without violating the separation between transaction storage and intelligence features.

### PHASE 10 — Analytics
- Objective: Add reporting and analytical views over purchasing and pricing data.
- Expected deliverables:
  - Spend and trend analysis capabilities
  - Supplier, category, and warehouse analytics
- Dependencies: Phase 9.
- Validation criteria:
  - Analytics remains separate from transaction persistence.
  - Core reporting use cases are validated.

### PHASE 11 — Dashboard
- Objective: Deliver a dashboard experience for operational and managerial oversight.
- Expected deliverables:
  - Dashboard views and KPI summaries
  - Supply Chain Manager oriented reporting
- Dependencies: Phase 10.
- Validation criteria:
  - Dashboard reflects the agreed KPI concepts.
  - The UI consumes analytics outputs rather than raw transaction storage directly.

### PHASE 12 — Production Hardening
- Objective: Prepare the system for production readiness.
- Expected deliverables:
  - Security, reliability, observability, and deployment hardening
  - Operational documentation and release controls
- Dependencies: Phase 11.
- Validation criteria:
  - The system is validated for production use.
  - Operational concerns are addressed before rollout.

---

## 13. Development Rules

The following rules govern implementation:

1. One architectural phase at a time.
2. Every phase must pass tests before moving forward.
3. Every completed phase gets a Git commit.
4. Never modify import logic while implementing unrelated infrastructure.
5. Never create duplicate SQLAlchemy Base classes.
6. Never create duplicate database/session modules.
7. Alembic must use the application’s single SQLAlchemy metadata.
8. PostgreSQL is the canonical runtime database.
9. No silent SQLite fallback.
10. Database migrations must be explicit and version controlled.
11. Do not invent business rules without approval.
12. Preserve working contracts when extending the system.
13. Avoid premature normalization.
14. Keep API transport separate from business logic.
15. Keep analytics separate from transactional persistence.

---

## 14. Git Strategy

The project will follow a simple Git strategy.

### main
- Stable, validated code only.

### Feature branches
- Feature branches may be created for larger phases.

### Commit expectations
- Every phase should have a meaningful commit.

Example commit messages:
- chore: initialize project foundation
- feat: add postgres infrastructure
- feat: add master data models
- feat: add initial database schema
- feat: add odoo transaction model
- feat: add odoo import engine
- feat: add import api
- feat: add procurement intelligence
- feat: add analytics layer

Branches and commits will not be created as part of this documentation-only task.

---

## 15. Architectural Safety

The project must never repeat the previous failure where application code existed only in an untracked workspace while GitHub contained an incomplete repository.

Therefore:

- Important source files must be tracked by Git.
- Each completed phase must be committed.
- Git status must be checked before phase completion.
- The remote repository must contain the completed phase.
- No phase is considered complete merely because local tests pass.

---

## 16. Definition of Done

A phase is considered DONE only when all of the following are true:

- Implementation is complete.
- Tests pass.
- No unintended files changed.
- Git diff reviewed.
- Git status reviewed.
- Commit created.
- Commit pushed to GitHub.
- Repository state matches local state.

---

## 17. Out of Scope for This Task

This task is documentation and architecture only.

The following are explicitly out of scope:

- No application code.
- No database.
- No Docker.
- No Alembic.
- No models.
- No API.
- No import engine.
- No migrations.
- No tests.

Only documentation is to be created for this task.
