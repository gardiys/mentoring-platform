"""Versioned legal offers, immutable checkout evidence and transactional email outbox."""

import json
from datetime import UTC, date, datetime, time
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "20261016_0100"
down_revision = "20261009_0099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE legal_offer_versions ( product_code VARCHAR(64) NOT NULL, version_code
        VARCHAR(32) NOT NULL, title VARCHAR(200) NOT NULL, publication_date DATE NOT NULL,
        effective_from TIMESTAMP WITH TIME ZONE NOT NULL, status VARCHAR(16) NOT NULL,
        pdf_storage_key VARCHAR(500) NOT NULL, markdown_storage_key VARCHAR(500), pdf_sha256
        VARCHAR(64) NOT NULL, markdown_sha256 VARCHAR(64), pdf_size INTEGER NOT NULL,
        pdf_mime_type VARCHAR(64) NOT NULL, financial_terms JSONB NOT NULL, activated_at
        TIMESTAMP WITH TIME ZONE, retired_at TIMESTAMP WITH TIME ZONE, revoked_at TIMESTAMP WITH
        TIME ZONE, id UUID NOT NULL, created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, CONSTRAINT
        pk_legal_offer_versions PRIMARY KEY (id), CONSTRAINT uq_legal_offer_version UNIQUE
        (product_code, version_code), CONSTRAINT ck_legal_offer_versions_legal_offer_status
        CHECK (status IN ('draft','active','retired','revoked')) )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_legal_offer_active ON legal_offer_versions (product_code) WHERE
        status = 'active'
        """
    )
    op.execute(
        """
        CREATE TABLE legal_checkouts ( user_id UUID NOT NULL, product_code VARCHAR(64) NOT NULL,
        application_id UUID NOT NULL, offer_version_id UUID NOT NULL, payment_id UUID, status
        VARCHAR(16) NOT NULL, expires_at TIMESTAMP WITH TIME ZONE NOT NULL, snapshot JSONB NOT
        NULL, id UUID NOT NULL, created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, CONSTRAINT
        pk_legal_checkouts PRIMARY KEY (id), CONSTRAINT ck_legal_checkouts_legal_checkout_status
        CHECK (status IN ('pending','paid','cancelled','expired')), CONSTRAINT
        fk_legal_checkouts_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE
        RESTRICT, CONSTRAINT fk_legal_checkouts_offer_version_id_legal_offer_versions FOREIGN
        KEY(offer_version_id) REFERENCES legal_offer_versions (id) ON DELETE RESTRICT,
        CONSTRAINT uq_legal_checkouts_payment_id UNIQUE (payment_id), CONSTRAINT
        fk_legal_checkouts_payment_id_opportunity_payment_attempts FOREIGN KEY(payment_id)
        REFERENCES opportunity_payment_attempts (id) ON DELETE RESTRICT )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_legal_checkout_pending ON legal_checkouts (application_id) WHERE
        status = 'pending'
        """
    )
    op.execute(
        """
        CREATE TABLE contract_acceptances ( public_number VARCHAR(64) NOT NULL, user_id UUID NOT
        NULL, product_code VARCHAR(64) NOT NULL, offer_version_id UUID NOT NULL,
        checkout_session_id UUID NOT NULL, payment_id UUID NOT NULL, accepted_at TIMESTAMP WITH
        TIME ZONE NOT NULL, provider_paid_at TIMESTAMP WITH TIME ZONE, webhook_received_at
        TIMESTAMP WITH TIME ZONE NOT NULL, snapshot JSONB NOT NULL, acceptance_snapshot_sha256
        VARCHAR(64) NOT NULL, status VARCHAR(16) NOT NULL, id UUID NOT NULL, created_at
        TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, updated_at TIMESTAMP WITH TIME ZONE
        DEFAULT now() NOT NULL, CONSTRAINT pk_contract_acceptances PRIMARY KEY (id), CONSTRAINT
        ck_contract_acceptances_contract_status CHECK (status IN
        ('active','terminated','refunded','disputed')), CONSTRAINT
        uq_contract_acceptances_public_number UNIQUE (public_number), CONSTRAINT
        fk_contract_acceptances_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON
        DELETE RESTRICT, CONSTRAINT
        fk_contract_acceptances_offer_version_id_legal_offer_versions FOREIGN
        KEY(offer_version_id) REFERENCES legal_offer_versions (id) ON DELETE RESTRICT,
        CONSTRAINT uq_contract_acceptances_checkout_session_id UNIQUE (checkout_session_id),
        CONSTRAINT fk_contract_acceptances_checkout_session_id_legal_checkouts FOREIGN
        KEY(checkout_session_id) REFERENCES legal_checkouts (id) ON DELETE RESTRICT, CONSTRAINT
        uq_contract_acceptances_payment_id UNIQUE (payment_id), CONSTRAINT
        fk_contract_acceptances_payment_id_opportunity_payment_attempts FOREIGN KEY(payment_id)
        REFERENCES opportunity_payment_attempts (id) ON DELETE RESTRICT )
        """
    )
    op.execute(
        """
        CREATE TABLE legal_email_deliveries ( contract_id UUID, notification_type VARCHAR(32)
        NOT NULL, attempt_number INTEGER NOT NULL, recipient_email VARCHAR(320) NOT NULL,
        subject_snapshot VARCHAR(500) NOT NULL, body_snapshot TEXT NOT NULL, attachment_sha256
        VARCHAR(64), provider_message_id VARCHAR(500), status VARCHAR(16) NOT NULL, retry_count
        INTEGER NOT NULL, next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL, sent_at TIMESTAMP
        WITH TIME ZONE, delivered_at TIMESTAMP WITH TIME ZONE, bounced_at TIMESTAMP WITH TIME
        ZONE, failed_at TIMESTAMP WITH TIME ZONE, error_code VARCHAR(64), safe_error_message
        VARCHAR(200), id UUID NOT NULL, created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT
        NULL, updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, CONSTRAINT
        pk_legal_email_deliveries PRIMARY KEY (id), CONSTRAINT uq_legal_email_attempt UNIQUE
        (contract_id, notification_type, attempt_number), CONSTRAINT
        ck_legal_email_deliveries_legal_email_status CHECK (status IN
        ('pending','processing','sent','delivered','bounced','failed')), CONSTRAINT
        fk_legal_email_deliveries_contract_id_contract_acceptances FOREIGN KEY(contract_id)
        REFERENCES contract_acceptances (id) ON DELETE RESTRICT, CONSTRAINT
        uq_legal_email_deliveries_provider_message_id UNIQUE (provider_message_id) )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_legal_email_due ON legal_email_deliveries (status, next_attempt_at)
        """
    )
    op.execute(
        """
        CREATE TABLE legal_email_verifications ( user_id UUID NOT NULL, email VARCHAR(320) NOT
        NULL, code_hash VARCHAR(64) NOT NULL, attempts INTEGER NOT NULL, expires_at TIMESTAMP
        WITH TIME ZONE NOT NULL, verified_at TIMESTAMP WITH TIME ZONE, id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, updated_at TIMESTAMP WITH
        TIME ZONE DEFAULT now() NOT NULL, CONSTRAINT pk_legal_email_verifications PRIMARY KEY
        (id), CONSTRAINT fk_legal_email_verifications_user_id_users FOREIGN KEY(user_id)
        REFERENCES users (id) ON DELETE RESTRICT )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_legal_email_verifications_user_id ON legal_email_verifications (user_id)
        """
    )
    op.execute(
        """
        CREATE TABLE legal_audit_events ( actor_id UUID, resource_id UUID, event_type
        VARCHAR(64) NOT NULL, payload JSONB NOT NULL, provider_event_id VARCHAR(255), id UUID
        NOT NULL, created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, updated_at
        TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, CONSTRAINT pk_legal_audit_events
        PRIMARY KEY (id), CONSTRAINT fk_legal_audit_events_actor_id_users FOREIGN KEY(actor_id)
        REFERENCES users (id) ON DELETE RESTRICT, CONSTRAINT
        uq_legal_audit_events_provider_event_id UNIQUE (provider_event_id) )
        """
    )
    op.execute("""
        CREATE INDEX ix_legal_audit_events_event_type ON legal_audit_events (event_type)
        """)
    op.execute("""
        CREATE INDEX ix_legal_audit_events_resource_id ON legal_audit_events (resource_id)
        """)
    op.execute(
        """
        CREATE TABLE legal_questionnaire_drafts ( user_id UUID NOT NULL, product_code
        VARCHAR(64) NOT NULL, schema_version INTEGER NOT NULL, answers JSONB NOT NULL, id UUID
        NOT NULL, created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, updated_at
        TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, CONSTRAINT
        pk_legal_questionnaire_drafts PRIMARY KEY (id), CONSTRAINT uq_legal_questionnaire_draft
        UNIQUE (user_id, product_code), CONSTRAINT fk_legal_questionnaire_drafts_user_id_users
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT )
        """
    )
    _seed_offer(
        {
            "product_code": "repeat_python_mentorship",
            "version_code": "2026-09-02",
            "publication_date": "2026-09-02",
            "pdf_storage_key": (
                "legal/offers/repeat-python-mentorship/2026-09-02/2f7a2c4e01609f37"
                "a9ebb04b7c93943d4f616cb2f55691ec409d41e9270bbd3f.pdf"
            ),
            "markdown_storage_key": (
                "legal/offers/repeat-python-mentorship/2026-09-02/c79a137a98c49754"
                "3d5b52e053cffef963768c514a25b51f224d4db80274ffa9.md"
            ),
            "pdf_sha256": "2f7a2c4e01609f37a9ebb04b7c93943d4f616cb2f55691ec409d41e9270bbd3f",
            "markdown_sha256": "c79a137a98c497543d5b52e053cffef963768c514a25b51f224d4db80274ffa9",
            "pdf_size": 383479,
            "title": "Повторное менторство по Python-разработке",
            "financial_terms": {
                "upfront_amount_minor": 3000000,
                "upfront_price_kopecks": 3000000,
                "currency": "RUB",
                "success_fee_percent": 100,
                "success_fee_is_additional": True,
                "success_fee_installments": 2,
                "success_fee_due_month_offsets": [1, 2],
                "minimum_success_fee_minor": None,
            },
        }
    )
    _seed_offer(
        {
            "product_code": "python_to_go_transition",
            "version_code": "2026-09-03",
            "publication_date": "2026-09-03",
            "pdf_storage_key": (
                "legal/offers/python-to-go-transition/2026-09-03/d5482491d8cc7c549"
                "7885000b618f94cf1b38922f529fa129bb1fd9e2c42811b.pdf"
            ),
            "markdown_storage_key": (
                "legal/offers/python-to-go-transition/2026-09-03/568a536665d42f56c"
                "7014fa19c51522be5fe54000ec4d0bd70a113abc959fd39.md"
            ),
            "pdf_sha256": "d5482491d8cc7c5497885000b618f94cf1b38922f529fa129bb1fd9e2c42811b",
            "markdown_sha256": "568a536665d42f56c7014fa19c51522be5fe54000ec4d0bd70a113abc959fd39",
            "pdf_size": 386750,
            "title": "Переход из Python-разработки в Go-разработку",
            "financial_terms": {
                "upfront_amount_minor": 3000000,
                "upfront_price_kopecks": 3000000,
                "currency": "RUB",
                "success_fee_percent": 100,
                "success_fee_is_additional": True,
                "success_fee_installments": 2,
                "success_fee_due_month_offsets": [1, 2],
                "minimum_success_fee_minor": None,
            },
        }
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION guard_legal_offer_versions() RETURNS trigger LANGUAGE plpgsql
        AS $$ BEGIN IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'legal evidence cannot be deleted'
        ; END IF; IF to_jsonb(OLD) - 'status' - 'activated_at' - 'retired_at' - 'revoked_at' -
        'updated_at' IS DISTINCT FROM to_jsonb(NEW) - 'status' - 'activated_at' - 'retired_at' -
        'revoked_at' - 'updated_at' THEN RAISE EXCEPTION 'legal evidence is immutable' ; END IF;
        RETURN NEW; END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER guard_legal_offer_versions BEFORE UPDATE OR DELETE ON
        legal_offer_versions FOR EACH ROW EXECUTE FUNCTION guard_legal_offer_versions()
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION guard_contract_acceptances() RETURNS trigger LANGUAGE plpgsql
        AS $$ BEGIN IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'legal evidence cannot be deleted'
        ; END IF; IF to_jsonb(OLD) - 'status' - 'updated_at' IS DISTINCT FROM to_jsonb(NEW) -
        'status' - 'updated_at' THEN RAISE EXCEPTION 'legal evidence is immutable' ; END IF;
        RETURN NEW; END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER guard_contract_acceptances BEFORE UPDATE OR DELETE ON
        contract_acceptances FOR EACH ROW EXECUTE FUNCTION guard_contract_acceptances()
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION guard_legal_checkouts() RETURNS trigger LANGUAGE plpgsql AS
        $$ BEGIN IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'legal evidence cannot be deleted' ;
        END IF; IF to_jsonb(OLD) - 'status' - 'updated_at' - 'payment_id' IS DISTINCT FROM
        to_jsonb(NEW) - 'status' - 'updated_at' - 'payment_id' THEN RAISE EXCEPTION
        'legal evidence is immutable' ; END IF; IF OLD.payment_id IS NOT NULL AND OLD.payment_id
        IS DISTINCT FROM NEW.payment_id THEN RAISE EXCEPTION 'immutable payment binding' ; END
        IF; RETURN NEW; END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER guard_legal_checkouts BEFORE UPDATE OR DELETE ON legal_checkouts FOR EACH
        ROW EXECUTE FUNCTION guard_legal_checkouts()
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION guard_legal_audit_events() RETURNS trigger LANGUAGE plpgsql
        AS $$ BEGIN IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'legal evidence cannot be deleted'
        ; END IF; IF to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN RAISE EXCEPTION
        'legal evidence is immutable' ; END IF; RETURN NEW; END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER guard_legal_audit_events BEFORE UPDATE OR DELETE ON legal_audit_events
        FOR EACH ROW EXECUTE FUNCTION guard_legal_audit_events()
        """
    )


def _seed_offer(data: dict) -> None:
    publication = date.fromisoformat(data.pop("publication_date"))
    op.execute(
        sa.text("""INSERT INTO legal_offer_versions
    (id, product_code, version_code, title, publication_date, effective_from, status,
     pdf_storage_key, markdown_storage_key, pdf_sha256, markdown_sha256, pdf_size,
     pdf_mime_type, financial_terms, activated_at)
    VALUES (:id, :product_code, :version_code, :title, :publication_date,
    :effective_from, 'active', :pdf_storage_key, :markdown_storage_key,
    :pdf_sha256, :markdown_sha256, :pdf_size, 'application/pdf',
    CAST(:terms AS jsonb), now())""").bindparams(
            id=uuid4(),
            publication_date=publication,
            effective_from=datetime.combine(publication, time.min, UTC),
            terms=json.dumps(data.pop("financial_terms")),
            **data,
        )
    )


def downgrade() -> None:
    # Explicit operator action is required: never delete legal evidence on rollback.
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM contract_acceptances")).scalar()
    if count:
        raise RuntimeError("Cannot downgrade with existing contracts; retain legal evidence")
    op.drop_table("legal_questionnaire_drafts")
    op.drop_table("legal_audit_events")
    op.drop_table("legal_email_verifications")
    op.drop_table("legal_email_deliveries")
    op.drop_table("contract_acceptances")
    op.drop_table("legal_checkouts")
    op.drop_table("legal_offer_versions")
    op.execute("""
        DROP FUNCTION guard_legal_offer_versions()
        """)
    op.execute("""
        DROP FUNCTION guard_contract_acceptances()
        """)
    op.execute("""
        DROP FUNCTION guard_legal_checkouts()
        """)
    op.execute("""
        DROP FUNCTION guard_legal_audit_events()
        """)
