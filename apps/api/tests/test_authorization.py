"""
Automated tests for ReleaseGate Identity, Organization Isolation,
RBAC (Role-Based Access Control), Persistent Inspections, and Cascading Integrity.
"""

import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.dataset import Dataset, DatasetVersion
from app.db.models.identity import Membership, Organization, User, UserRole
from app.db.models.inspection import (
    Finding,
    FindingType,
    InspectionRun,
    InspectionStatus,
    InspectionType,
)
from app.schemas.dataset import (
    DatasetMetadataRegistrationRequest,
    DatasetProfileSchema,
)
from app.schemas.identity import MembershipCreate, OrganizationCreate, UserCreate
from app.schemas.inspection import FindingCreate, InspectionRunCreate
from app.services.dataset_service import (
    CrossOrganizationAccessError as DatasetCrossOrgError,
    DatasetNotFoundError,
    DatasetService,
)
from app.services.identity_service import (
    DuplicateEntityError,
    IdentityService,
    InsufficientPermissionsError,
    OrganizationAccessDeniedError,
    hash_password,
    verify_password,
)
from app.services.inspection_service import (
    CrossOrganizationAccessError as InspectionCrossOrgError,
    InspectionRunNotFoundError,
    InspectionService,
)


def _make_dummy_profile(
    row_count: int = 100,
    columns: list = None,
    column_types: dict = None,
) -> DatasetProfileSchema:
    if columns is None:
        columns = ["id", "val"]
    if column_types is None:
        column_types = {c: "int64" for c in columns}
    return DatasetProfileSchema(
        row_count=row_count,
        column_count=len(columns),
        columns=columns,
        column_types=column_types,
        null_counts={c: 0 for c in columns},
        null_percentages={c: 0.0 for c in columns},
        duplicate_row_count=0,
        file_format="csv",
    )


def test_password_hashing_and_verification():
    """Verify cryptographic password hashing with unique salt and verification."""
    password = "SuperSecretReleasePassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert "$" in hashed
    parts = hashed.split("$")
    assert len(parts) == 2
    assert len(parts[0]) == 32  # 16-byte hex salt
    assert len(parts[1]) == 64  # sha256 hex digest

    # Correct password matches
    assert verify_password(password, hashed) is True

    # Incorrect password fails
    assert verify_password("WrongPassword!", hashed) is False

    # Salt randomness ensures different hashes for the same password
    hashed_again = hash_password(password)
    assert hashed != hashed_again
    assert verify_password(password, hashed_again) is True


def test_organization_and_user_creation(db_session: Session):
    """Test organization and user account creation and unique constraint protections."""
    id_svc = IdentityService()

    org = id_svc.create_organization(
        OrganizationCreate(name="Acme AI Labs", slug="acme-ai"),
        db=db_session,
    )
    assert org.id is not None
    assert org.name == "Acme AI Labs"
    assert org.slug == "acme-ai"

    # Duplicate name or slug must raise DuplicateEntityError
    with pytest.raises(DuplicateEntityError):
        id_svc.create_organization(
            OrganizationCreate(name="Acme AI Labs", slug="acme-unique"),
            db=db_session,
        )
    with pytest.raises(DuplicateEntityError):
        id_svc.create_organization(
            OrganizationCreate(name="Different Name", slug="acme-ai"),
            db=db_session,
        )

    # User creation
    user = id_svc.create_user(
        UserCreate(
            email="steward@acme.ai",
            password="StrongPassword2026!",
            full_name="Alice Steward",
        ),
        db=db_session,
    )
    assert user.id is not None
    assert user.email == "steward@acme.ai"
    assert verify_password("StrongPassword2026!", db_session.get(User, user.id).hashed_password) is True

    # Duplicate email rejection
    with pytest.raises(DuplicateEntityError):
        id_svc.create_user(
            UserCreate(email="steward@acme.ai", password="AnotherPassword999!"),
            db=db_session,
        )


def test_rbac_membership_assignment_and_hierarchy(db_session: Session):
    """Test RBAC role assignment and hierarchical permission checks."""
    id_svc = IdentityService()

    org = id_svc.create_organization(OrganizationCreate(name="FinTech Corp", slug="fintech-corp"), db=db_session)
    admin_user = id_svc.create_user(UserCreate(email="admin@fintech.corp", password="Password123!"), db=db_session)
    steward_user = id_svc.create_user(UserCreate(email="steward@fintech.corp", password="Password123!"), db=db_session)
    auditor_user = id_svc.create_user(UserCreate(email="auditor@fintech.corp", password="Password123!"), db=db_session)
    plain_user = id_svc.create_user(UserCreate(email="analyst@fintech.corp", password="Password123!"), db=db_session)

    # Assign roles
    id_svc.assign_membership(MembershipCreate(organization_id=org.id, user_id=admin_user.id, role=UserRole.ADMIN), db=db_session)
    id_svc.assign_membership(MembershipCreate(organization_id=org.id, user_id=steward_user.id, role=UserRole.STEWARD), db=db_session)
    id_svc.assign_membership(MembershipCreate(organization_id=org.id, user_id=auditor_user.id, role=UserRole.AUDITOR), db=db_session)
    id_svc.assign_membership(MembershipCreate(organization_id=org.id, user_id=plain_user.id, role=UserRole.USER), db=db_session)

    # ADMIN has full permissions: admin, write, audit, read, approve
    admin_m = id_svc.require_organization_access(admin_user.id, org.id, db=db_session, required_permission="admin")
    assert admin_m.role == UserRole.ADMIN.value

    # STEWARD has write, audit, approve, read, but NOT admin
    steward_m = id_svc.require_organization_access(steward_user.id, org.id, db=db_session, required_permission="approve")
    assert steward_m.role == UserRole.STEWARD.value
    with pytest.raises(InsufficientPermissionsError):
        id_svc.require_organization_access(steward_user.id, org.id, db=db_session, required_permission="admin")

    # AUDITOR has read and audit, but NOT write or approve
    auditor_m = id_svc.require_organization_access(auditor_user.id, org.id, db=db_session, required_permission="audit")
    assert auditor_m.role == UserRole.AUDITOR.value
    with pytest.raises(InsufficientPermissionsError):
        id_svc.require_organization_access(auditor_user.id, org.id, db=db_session, required_permission="write")

    # Plain USER has read and write, but NOT audit or approve
    user_m = id_svc.require_organization_access(plain_user.id, org.id, db=db_session, required_permission="write")
    assert user_m.role == UserRole.USER.value
    with pytest.raises(InsufficientPermissionsError):
        id_svc.require_organization_access(plain_user.id, org.id, db=db_session, required_permission="audit")

    # Allowed roles check
    id_svc.require_organization_access(admin_user.id, org.id, db=db_session, allowed_roles={UserRole.ADMIN})
    with pytest.raises(InsufficientPermissionsError):
        id_svc.require_organization_access(plain_user.id, org.id, db=db_session, allowed_roles={UserRole.ADMIN})


def test_organization_data_isolation_datasets(db_session: Session):
    """
    Test that datasets are strictly isolated by organization:
    Users from Org A cannot access, query, or enumerate datasets belonging to Org B.
    """
    id_svc = IdentityService()
    ds_svc = DatasetService()

    org_a = id_svc.create_organization(OrganizationCreate(name="HealthCare AI", slug="healthcare-ai"), db=db_session)
    org_b = id_svc.create_organization(OrganizationCreate(name="Finance AI", slug="finance-ai"), db=db_session)

    user_a = id_svc.create_user(UserCreate(email="alice@healthcare.ai", password="Password123!"), db=db_session)
    user_b = id_svc.create_user(UserCreate(email="bob@finance.ai", password="Password123!"), db=db_session)

    # Org A registers a dataset
    reg_a = DatasetMetadataRegistrationRequest(
        dataset_name="Clinical Patients v1",
        description="Encrypted health metrics",
        content_hash="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        file_format="csv",
        file_size=1024,
        local_artifact_ref="artifact://local/datasets/sample-a/v1/clinical.csv",
        profile=_make_dummy_profile(row_count=100, columns=["id", "age"]),
    )
    dataset_a = ds_svc.register_dataset_metadata(reg_a, db=db_session, organization_id=org_a.id, created_by=user_a.id)

    # Org B registers a dataset
    reg_b = DatasetMetadataRegistrationRequest(
        dataset_name="Credit Default v1",
        description="Risk scoring demographics",
        content_hash="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        file_format="csv",
        file_size=2048,
        local_artifact_ref="artifact://local/datasets/sample-b/v1/credit.csv",
        profile=_make_dummy_profile(row_count=200, columns=["id", "balance"]),
    )
    dataset_b = ds_svc.register_dataset_metadata(reg_b, db=db_session, organization_id=org_b.id, created_by=user_b.id)

    # User A can get Dataset A
    retrieved_a = ds_svc.get_dataset(dataset_a.dataset_id, db=db_session, organization_id=org_a.id)
    assert retrieved_a.id == dataset_a.dataset_id

    # User A CANNOT get Dataset B (boundary check raises DatasetCrossOrgError)
    with pytest.raises(DatasetCrossOrgError):
        ds_svc.get_dataset(dataset_b.dataset_id, db=db_session, organization_id=org_a.id)

    # List datasets for Org A must return ONLY Dataset A
    org_a_datasets = ds_svc.list_datasets(db=db_session, organization_id=org_a.id)
    assert len(org_a_datasets) == 1
    assert org_a_datasets[0].id == dataset_a.dataset_id

    # List datasets for Org B must return ONLY Dataset B
    org_b_datasets = ds_svc.list_datasets(db=db_session, organization_id=org_b.id)
    assert len(org_b_datasets) == 1
    assert org_b_datasets[0].id == dataset_b.dataset_id


def test_organization_data_isolation_inspections_and_findings(db_session: Session):
    """
    Test that persistent inspection runs and findings are strictly bound to organization_id.
    Cross-organization retrieval attempts must fail closed.
    """
    id_svc = IdentityService()
    ds_svc = DatasetService()
    insp_svc = InspectionService()

    org_a = id_svc.create_organization(OrganizationCreate(name="Org Alpha", slug="org-alpha"), db=db_session)
    org_b = id_svc.create_organization(OrganizationCreate(name="Org Beta", slug="org-beta"), db=db_session)

    user_a = id_svc.create_user(UserCreate(email="alpha@org.com", password="Password123!"), db=db_session)

    # Org A dataset and version
    reg_a = DatasetMetadataRegistrationRequest(
        dataset_name="Alpha Set",
        content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        file_format="csv",
        file_size=500,
        local_artifact_ref="artifact://local/datasets/alpha/v1/alpha.csv",
        profile=_make_dummy_profile(
            row_count=1000,
            columns=["user_id", "email", "score"],
            column_types={"user_id": "int64", "email": "object", "score": "float64"},
        ),
    )
    dataset_a = ds_svc.register_dataset_metadata(reg_a, db=db_session, organization_id=org_a.id, created_by=user_a.id)

    # Record persistent inspection run with findings for Org A
    run_create = InspectionRunCreate(
        dataset_id=dataset_a.dataset_id,
        dataset_version_id=dataset_a.version_id,
        inspection_type=InspectionType.PII_DETECTION,
        status=InspectionStatus.COMPLETED,
        risk_score=35.0,
        risk_band="MODERATE",
        policy_version="1.0.0",
        is_release_eligible=True,
        summary_report={"pii_findings_count": 2, "high_severity": 1},
        findings=[
            FindingCreate(
                finding_type=FindingType.PII,
                category="EMAIL_ADDRESS",
                column_name="email",
                severity="HIGH",
                occurrence_count=12,
                confidence_score=0.95,
                message="Detected 12 email addresses",
                evidence_ref={"rule": "presidio_email_detector", "hash": "abc123"},
            ),
            FindingCreate(
                finding_type=FindingType.PII,
                category="PHONE_NUMBER",
                column_name="phone",
                severity="MEDIUM",
                occurrence_count=5,
                confidence_score=0.85,
                message="Detected 5 phone numbers",
                evidence_ref={"rule": "presidio_phone_detector", "hash": "def456"},
            ),
        ],
    )

    run = insp_svc.record_inspection_run(org_a.id, run_create, db=db_session)
    assert run.id is not None
    assert run.organization_id == org_a.id
    assert len(run.findings) == 2

    # Retrieval inside Org A succeeds
    fetched_run = insp_svc.get_inspection_run(org_a.id, run.id, db=db_session)
    assert fetched_run.id == run.id
    assert len(fetched_run.findings) == 2

    # Cross-tenant retrieval from Org B raises InspectionRunNotFoundError (fail closed)
    with pytest.raises(InspectionRunNotFoundError):
        insp_svc.get_inspection_run(org_b.id, run.id, db=db_session)

    # Listing inspection runs for Org B returns empty list
    runs_b = insp_svc.list_inspection_runs_for_dataset(org_b.id, dataset_a.dataset_id, db=db_session)
    assert len(runs_b) == 0

    # Listing findings for Org B returns empty list
    findings_b = insp_svc.list_findings_for_version(org_b.id, dataset_a.version_id, db=db_session)
    assert len(findings_b) == 0

    # Listing findings for Org A returns the 2 recorded findings
    findings_a = insp_svc.list_findings_for_version(org_a.id, dataset_a.version_id, db=db_session)
    assert len(findings_a) == 2


def test_immutable_dataset_version_unique_constraint(db_session: Session):
    """
    Test that dataset versions are strictly immutable and enforce
    the (dataset_id, version_number) unique constraint.
    """
    id_svc = IdentityService()
    ds_svc = DatasetService()

    org = id_svc.create_organization(OrganizationCreate(name="Immutable Org", slug="immutable-org"), db=db_session)
    user = id_svc.create_user(UserCreate(email="data@immutable.org", password="Password123!"), db=db_session)

    reg = DatasetMetadataRegistrationRequest(
        dataset_name="Demographics",
        content_hash="1111111111111111111111111111111111111111111111111111111111111111",
        file_format="csv",
        file_size=500,
        local_artifact_ref="artifact://local/datasets/demo/v1/demo.csv",
        profile=_make_dummy_profile(row_count=100, columns=["id", "name"]),
    )
    dataset = ds_svc.register_dataset_metadata(reg, db=db_session, organization_id=org.id, created_by=user.id)

    # Attempting to create duplicate version 1 for the same dataset must fail integrity constraint
    with pytest.raises(IntegrityError):
        dup_version = DatasetVersion(
            id=uuid.uuid4(),
            dataset_id=dataset.dataset_id,
            version_number=1,
            content_hash="2222222222222222222222222222222222222222222222222222222222222222",
            file_format="csv",
            file_size=600,
            local_artifact_ref="artifact://local/datasets/demo/v1/demo_dup.csv",
            dataset_metadata={},
        )
        db_session.add(dup_version)
        db_session.commit()
    db_session.rollback()


def test_cascading_deletion_and_relational_integrity(db_session: Session):
    """
    Test foreign key relationships and cascading deletion rules:
    Deleting an Organization cascades cleanly to Memberships, Datasets, Versions,
    InspectionRuns, and Findings.
    """
    id_svc = IdentityService()
    ds_svc = DatasetService()
    insp_svc = InspectionService()

    org = id_svc.create_organization(OrganizationCreate(name="Ephemeral Org", slug="ephemeral-org"), db=db_session)
    user = id_svc.create_user(UserCreate(email="user@ephemeral.org", password="Password123!"), db=db_session)
    id_svc.assign_membership(MembershipCreate(organization_id=org.id, user_id=user.id, role=UserRole.ADMIN), db=db_session)

    reg = DatasetMetadataRegistrationRequest(
        dataset_name="Ephemeral Data",
        content_hash="3333333333333333333333333333333333333333333333333333333333333333",
        file_format="csv",
        file_size=200,
        local_artifact_ref="artifact://local/datasets/ephemeral/v1/data.csv",
        profile=_make_dummy_profile(row_count=50, columns=["id"]),
    )
    dataset = ds_svc.register_dataset_metadata(reg, db=db_session, organization_id=org.id, created_by=user.id)

    run = insp_svc.record_inspection_run(
        org.id,
        InspectionRunCreate(
            dataset_id=dataset.dataset_id,
            dataset_version_id=dataset.version_id,
            inspection_type=InspectionType.QUALITY_VALIDATION,
            status=InspectionStatus.COMPLETED,
            risk_score=0.0,
            policy_version="1.0.0",
            findings=[
                FindingCreate(
                    finding_type=FindingType.QUALITY,
                    category="MISSING_VALUES",
                    column_name="id",
                    severity="LOW",
                    occurrence_count=1,
                    confidence_score=1.0,
                    message="No missing values",
                    evidence_ref={},
                )
            ],
        ),
        db=db_session,
    )

    org_id = org.id

    # Verify counts before deletion
    assert db_session.query(Organization).filter_by(id=org_id).count() == 1
    assert db_session.query(Membership).filter_by(organization_id=org_id).count() == 1
    assert db_session.query(Dataset).filter_by(organization_id=org_id).count() == 1
    assert db_session.query(DatasetVersion).filter_by(dataset_id=dataset.dataset_id).count() == 1
    assert db_session.query(InspectionRun).filter_by(organization_id=org_id).count() == 1
    assert db_session.query(Finding).filter_by(organization_id=org_id).count() == 1

    # Retrieve and delete organization
    org_orm = db_session.get(Organization, org_id)
    db_session.delete(org_orm)
    db_session.commit()

    # Verify cascading deletion
    assert db_session.query(Organization).filter_by(id=org_id).count() == 0
    assert db_session.query(Membership).filter_by(organization_id=org_id).count() == 0
    assert db_session.query(Dataset).filter_by(organization_id=org_id).count() == 0
    assert db_session.query(DatasetVersion).filter_by(dataset_id=dataset.dataset_id).count() == 0
    assert db_session.query(InspectionRun).filter_by(organization_id=org_id).count() == 0
    assert db_session.query(Finding).filter_by(organization_id=org_id).count() == 0

    # User remains intact (not deleted by org cascade)
    assert db_session.query(User).filter_by(id=user.id).count() == 1


def test_alembic_migration_from_empty_database():
    """
    Test running Alembic migration against an empty SQLite/PostgreSQL-compatible database.
    Verifies that all 7 baseline entities and their columns, foreign keys, and indexes are created.
    """
    import os
    import tempfile
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import create_engine, inspect

    with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db:
        db_url = f"sqlite:///{tmp_db.name}"
        alembic_cfg = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        # Execute migration upgrade to head
        command.upgrade(alembic_cfg, "head")

        # Inspect resulting tables
        tmp_engine = create_engine(db_url)
        inspector = inspect(tmp_engine)
        table_names = set(inspector.get_table_names())

        expected_tables = {
            "organizations",
            "users",
            "memberships",
            "datasets",
            "dataset_versions",
            "inspection_runs",
            "findings",
        }
        assert expected_tables.issubset(table_names), f"Missing tables: {expected_tables - table_names}"

        # Verify columns on inspection_runs
        run_cols = {col["name"] for col in inspector.get_columns("inspection_runs")}
        assert {"id", "organization_id", "dataset_id", "dataset_version_id", "risk_score", "risk_band"}.issubset(run_cols)

        # Verify columns on findings
        finding_cols = {col["name"] for col in inspector.get_columns("findings")}
        assert {"id", "organization_id", "inspection_run_id", "dataset_version_id", "category", "severity"}.issubset(finding_cols)

