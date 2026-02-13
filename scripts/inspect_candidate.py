#!/usr/bin/env python3
"""Inspect a candidate's normalized data by partition ID (airtable_record_id).

Usage:
    python scripts/inspect_candidate.py <partition_id>
    python scripts/inspect_candidate.py rechGJvgloO4z6uYD

This script displays all normalized information about a candidate including:
- Raw candidate data
- Normalized profile
- Skills, experiences, and projects (if populated)
- Vector embeddings status
"""

import os
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

import psycopg2  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402


def get_connection():
    """Create database connection."""
    return psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )


def format_value(value, max_length: int | None = None) -> str:
    """Format a value for display, optionally truncating.

    Args:
        value: The value to format
        max_length: Maximum length before truncating. None = no truncation.
    """
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, list):
        if not value:
            return "[]"
        items = ", ".join(str(v) for v in value)
        return f"[{items}]"
    val_str = str(value)
    if max_length and len(val_str) > max_length:
        return val_str[:max_length] + "..."
    return val_str


def print_section(title: str):
    """Print a section header."""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_field(name: str, value, indent: int = 0, max_length: int | None = None):
    """Print a field with optional indentation.

    Args:
        name: Field name
        value: Field value
        indent: Number of indentation levels
        max_length: Optional max length for truncation
    """
    prefix = "  " * indent
    formatted = format_value(value, max_length=max_length)
    print(f"{prefix}{name}: {formatted}")


def inspect_candidate(partition_id: str):
    """Inspect all data for a candidate."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ─────────────────────────────────────────────────────────────
    # RAW CANDIDATE
    # ─────────────────────────────────────────────────────────────
    print_section("RAW CANDIDATE DATA")

    cur.execute(
        "SELECT * FROM raw_candidates WHERE airtable_record_id = %s",
        (partition_id,),
    )
    raw = cur.fetchone()

    if not raw:
        print(f"  ❌ No raw candidate found with partition_id: {partition_id}")
        cur.close()
        conn.close()
        return

    # Show ALL raw candidate fields
    print_field("ID", raw["id"])
    print_field("Airtable Record ID", raw["airtable_record_id"])
    print_field("Source", raw["source"])
    print_field("Source ID", raw["source_id"])
    print_field("Full Name", raw["full_name"])
    print_field("Location", raw["location_raw"])
    print_field("Job Categories", raw["desired_job_categories_raw"])
    print_field("Skills", raw["skills_raw"])
    print_field("CV URL", raw["cv_url"])
    print_field("CV Text", raw["cv_text"])
    print_field("Professional Summary", raw["professional_summary"])
    print_field("Proof of Work", raw["proof_of_work"])
    print_field("Salary Range", raw["salary_range_raw"])
    print_field("X Profile", raw["x_profile_url"])
    print_field("LinkedIn", raw["linkedin_url"])
    print_field("Earn Profile", raw["earn_profile_url"])
    print_field("GitHub", raw["github_url"])
    print_field("Work Experience Raw", raw["work_experience_raw"])
    print_field("Ingested At", raw["ingested_at"])
    print_field("Updated At", raw["updated_at"])
    print_field("Processing Status", raw["processing_status"])
    print_field("Processing Error", raw["processing_error"])

    # ─────────────────────────────────────────────────────────────
    # NORMALIZED CANDIDATE
    # ─────────────────────────────────────────────────────────────
    print_section("NORMALIZED CANDIDATE PROFILE")

    cur.execute(
        "SELECT * FROM normalized_candidates WHERE airtable_record_id = %s",
        (partition_id,),
    )
    normalized = cur.fetchone()

    if not normalized:
        print("  ❌ Not yet normalized (run the normalization pipeline)")
    else:
        normalized_id = normalized["id"]

        print("\n  📋 BASIC INFO")
        print_field("ID", normalized["id"], 1)
        print_field("Raw Candidate ID", normalized["raw_candidate_id"], 1)
        print_field("Full Name", normalized["full_name"], 1)
        print_field("Email", normalized["email"], 1)
        print_field("Phone", normalized["phone"], 1)
        print_field("Current Role", normalized["current_role"], 1)
        print_field("Seniority Level", normalized["seniority_level"], 1)
        print_field("Years of Experience", normalized["years_of_experience"], 1)

        print("\n  📍 LOCATION")
        print_field("City", normalized["location_city"], 1)
        print_field("Country", normalized["location_country"], 1)
        print_field("Region", normalized["location_region"], 1)
        print_field("Timezone", normalized["timezone"], 1)

        print("\n  💼 PROFESSIONAL")
        print_field("Summary", normalized["professional_summary"], 1)
        print_field("Job Categories", normalized["desired_job_categories"], 1)
        print_field("Skills", normalized["skills_summary"], 1)
        print_field("Companies", normalized["companies_summary"], 1)
        print_field("Notable Achievements", normalized["notable_achievements"], 1)
        print_field("Verified Communities", normalized["verified_communities"], 1)

        print("\n  📊 CAREER STATS")
        print_field("Job Count", normalized["job_count"], 1)
        print_field("Job Switches", normalized["job_switches_count"], 1)
        print_field("Average Tenure (months)", normalized["average_tenure_months"], 1)
        print_field("Longest Tenure (months)", normalized["longest_tenure_months"], 1)

        print("\n  💰 COMPENSATION")
        print_field("Min", normalized["compensation_min"], 1)
        print_field("Max", normalized["compensation_max"], 1)
        print_field("Currency", normalized["compensation_currency"], 1)

        print("\n  🎓 EDUCATION")
        print_field("Highest Degree", normalized["education_highest_degree"], 1)
        print_field("Field", normalized["education_field"], 1)
        print_field("Institution", normalized["education_institution"], 1)

        print("\n  🏆 HACKATHONS")
        print_field("Wins Count", normalized["hackathon_wins_count"], 1)
        print_field("Total Prize (USD)", normalized["hackathon_total_prize_usd"], 1)
        print_field("Solana Wins", normalized["solana_hackathon_wins"], 1)

        print("\n  🔗 SOCIAL HANDLES")
        print_field("X/Twitter", normalized["x_handle"], 1)
        print_field("LinkedIn", normalized["linkedin_handle"], 1)
        print_field("GitHub", normalized["github_handle"], 1)
        print_field("Total Followers", normalized["social_followers_total"], 1)

        print("\n  ✅ VERIFICATION")
        print_field("Status", normalized["verification_status"], 1)
        print_field("Notes", normalized["verification_notes"], 1)
        print_field("Verified By", normalized["verified_by"], 1)
        print_field("Verified At", normalized["verified_at"], 1)

        print("\n  🤖 LLM METADATA")
        print_field("Model Version", normalized["model_version"], 1)
        print_field("Prompt Version", normalized["prompt_version"], 1)
        print_field("Confidence Score", normalized["confidence_score"], 1)
        print_field("Normalized At", normalized["normalized_at"], 1)

        # ─────────────────────────────────────────────────────────
        # SKILLS (Related Table)
        # ─────────────────────────────────────────────────────────
        print_section("CANDIDATE SKILLS (Related Table)")

        cur.execute(
            """SELECT cs.rating, cs.years_experience, cs.notable_achievement,
                      s.name as skill_name
               FROM candidate_skills cs
               LEFT JOIN skills s ON cs.skill_id = s.id
               WHERE cs.candidate_id = %s
               ORDER BY cs.rating DESC NULLS LAST""",
            (normalized_id,),
        )
        skills = cur.fetchall()

        if not skills:
            print("  (No skills in related table - data is in skills_summary array)")
        else:
            for skill in skills:
                print(
                    f"  • {skill['skill_name'] or 'Unknown'} "
                    f"(rating: {skill['rating']}/10, years: {skill['years_experience']})"
                )
                if skill["notable_achievement"]:
                    print(f"    Achievement: {format_value(skill['notable_achievement'])}")

        # ─────────────────────────────────────────────────────────
        # WORK EXPERIENCE (Related Table)
        # ─────────────────────────────────────────────────────────
        print_section("WORK EXPERIENCE (Related Table)")

        cur.execute(
            """SELECT company_name, position_title, years_experience, description,
                      skills_used, is_current, start_date, end_date
               FROM candidate_experiences WHERE candidate_id = %s
               ORDER BY position_order, start_date DESC NULLS LAST""",
            (normalized_id,),
        )
        experiences = cur.fetchall()

        if not experiences:
            print("  (No experiences in related table - data is in companies_summary array)")
        else:
            for i, exp in enumerate(experiences, 1):
                current = " (current)" if exp["is_current"] else ""
                print(f"\n  [{i}] {exp['position_title']} at {exp['company_name']}{current}")
                print_field("Years", exp["years_experience"], 2)
                end_str = "present" if exp["is_current"] else (exp["end_date"] or "—")
                print_field("Period", f"{exp['start_date'] or '—'} to {end_str}", 2)
                print_field("Description", exp["description"], 2)
                print_field("Skills Used", exp["skills_used"], 2)

        # ─────────────────────────────────────────────────────────
        # PROJECTS (Related Table)
        # ─────────────────────────────────────────────────────────
        print_section("PROJECTS (Related Table)")

        cur.execute(
            """SELECT project_name, description, url, technologies,
                      is_hackathon, hackathon_name, prize_won, prize_amount_usd, year
               FROM candidate_projects WHERE candidate_id = %s
               ORDER BY project_order, year DESC NULLS LAST""",
            (normalized_id,),
        )
        projects = cur.fetchall()

        if not projects:
            print("  (No projects in related table)")
        else:
            for i, proj in enumerate(projects, 1):
                hackathon = " 🏆" if proj["is_hackathon"] else ""
                print(f"\n  [{i}] {proj['project_name']}{hackathon}")
                print_field("Description", proj["description"], 2)
                print_field("URL", proj["url"], 2)
                print_field("Technologies", proj["technologies"], 2)
                print_field("Year", proj["year"], 2)
                if proj["is_hackathon"]:
                    print_field("Hackathon", proj["hackathon_name"], 2)
                    print_field("Prize Won", proj["prize_won"], 2)
                    print_field("Prize Amount (USD)", proj["prize_amount_usd"], 2)

    # ─────────────────────────────────────────────────────────────
    # VECTOR EMBEDDINGS
    # ─────────────────────────────────────────────────────────────
    print_section("VECTOR EMBEDDINGS")

    if normalized:
        cur.execute(
            """SELECT vector_type, model_version, created_at,
                      vector_dims(vector) as dimensions
               FROM candidate_vectors WHERE candidate_id = %s""",
            (normalized_id,),
        )
        vectors = cur.fetchall()

        if not vectors:
            print("  ❌ No embeddings yet (run the candidate_vectors asset)")
        else:
            for vec in vectors:
                print(
                    f"  ✅ {vec['vector_type']}: {vec['dimensions']} dimensions "
                    f"(model: {vec['model_version']}, created: {format_value(vec['created_at'])})"
                )
    else:
        print("  ❌ Candidate not normalized yet - no vectors possible")

    cur.close()
    conn.close()

    print()
    print("=" * 60)
    print("  END OF REPORT")
    print("=" * 60)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/inspect_candidate.py <partition_id>")
        print("Example: python scripts/inspect_candidate.py rechGJvgloO4z6uYD")
        sys.exit(1)

    partition_id = sys.argv[1]
    print(f"\n🔍 Inspecting candidate: {partition_id}\n")
    inspect_candidate(partition_id)


if __name__ == "__main__":
    main()
