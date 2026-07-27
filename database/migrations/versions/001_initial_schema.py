"""Initial schema creation for Phase 1.

Creates all tables:
- candidates
- resumes
- parsed_data
- skills
- education
- experience

Revision ID: 001
Revises: None
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa


revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all Phase 1 tables."""
    
    # Create candidates table
    op.create_table(
        "candidates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_candidates_id"), "candidates", ["id"], unique=False)
    op.create_index(op.f("ix_candidates_name"), "candidates", ["name"], unique=False)
    op.create_index(op.f("ix_candidates_email"), "candidates", ["email"], unique=False)

    # Create resumes table
    op.create_table(
        "resumes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="uploaded"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("parsed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_resumes_id"), "resumes", ["id"], unique=False)
    op.create_index(op.f("ix_resumes_candidate_id"), "resumes", ["candidate_id"], unique=False)

    # Create parsed_data table
    op.create_table(
        "parsed_data",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resume_id", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("structured_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resume_id"),
    )
    op.create_index(op.f("ix_parsed_data_id"), "parsed_data", ["id"], unique=False)
    op.create_index(op.f("ix_parsed_data_resume_id"), "parsed_data", ["resume_id"], unique=False)

    # Create skills table
    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("skill_name", sa.String(255), nullable=False),
        sa.Column("proficiency_level", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_skills_id"), "skills", ["id"], unique=False)
    op.create_index(op.f("ix_skills_candidate_id"), "skills", ["candidate_id"], unique=False)
    op.create_index(op.f("ix_skills_skill_name"), "skills", ["skill_name"], unique=False)

    # Create education table
    op.create_table(
        "education",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("institution_name", sa.String(255), nullable=False),
        sa.Column("degree_name", sa.String(255), nullable=True),
        sa.Column("field_of_study", sa.String(255), nullable=True),
        sa.Column("start_year", sa.Integer(), nullable=True),
        sa.Column("end_year", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_education_id"), "education", ["id"], unique=False)
    op.create_index(op.f("ix_education_candidate_id"), "education", ["candidate_id"], unique=False)

    # Create experience table
    op.create_table(
        "experience",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("job_title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_date", sa.String(50), nullable=True),
        sa.Column("end_date", sa.String(50), nullable=True),
        sa.Column("is_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_experience_id"), "experience", ["id"], unique=False)
    op.create_index(op.f("ix_experience_candidate_id"), "experience", ["candidate_id"], unique=False)


def downgrade() -> None:
    """Drop all Phase 1 tables."""
    op.drop_table("experience")
    op.drop_table("education")
    op.drop_table("skills")
    op.drop_table("parsed_data")
    op.drop_table("resumes")
    op.drop_table("candidates")
