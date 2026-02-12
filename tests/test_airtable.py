"""Tests for Airtable integration components.

This module tests:
- AirtableResource API interactions (mocked)
- Field mapping utilities
- CV URL extraction
- Data versioning
"""

from unittest.mock import MagicMock, patch

import pytest

from talent_matching.resources.airtable import AirtableResource
from talent_matching.utils.airtable_mapper import (
    extract_cv_url,
    map_airtable_row_to_raw_candidate,
    parse_comma_separated,
)


class TestExtractCvUrl:
    """Tests for CV URL extraction from various formats."""

    def test_extract_from_airtable_attachment_list(self):
        """Test extracting URL from Airtable API attachment format."""
        cv_field = [{"url": "https://example.com/cv.pdf", "filename": "resume.pdf"}]
        result = extract_cv_url(cv_field)
        assert result == "https://example.com/cv.pdf"

    def test_extract_from_csv_format(self):
        """Test extracting URL from CSV export format."""
        cv_field = "Mayank-Rawat-Fullstack.pdf (https://v5.airtableusercontent.com/v3/u/50/50/123)"
        result = extract_cv_url(cv_field)
        assert result == "https://v5.airtableusercontent.com/v3/u/50/50/123"

    def test_extract_from_plain_url(self):
        """Test extracting plain URL without filename prefix."""
        cv_field = "https://example.com/cv.pdf"
        result = extract_cv_url(cv_field)
        assert result == "https://example.com/cv.pdf"

    def test_extract_from_http_url(self):
        """Test extracting HTTP (non-HTTPS) URL."""
        cv_field = "http://example.com/cv.pdf"
        result = extract_cv_url(cv_field)
        assert result == "http://example.com/cv.pdf"

    def test_returns_none_for_empty_list(self):
        """Test that empty attachment list returns None."""
        result = extract_cv_url([])
        assert result is None

    def test_returns_none_for_none_input(self):
        """Test that None input returns None."""
        result = extract_cv_url(None)
        assert result is None

    def test_returns_none_for_invalid_string(self):
        """Test that string without URL returns None."""
        result = extract_cv_url("just a filename.pdf")
        assert result is None

    def test_handles_whitespace(self):
        """Test that whitespace is handled correctly."""
        cv_field = "  https://example.com/cv.pdf  "
        result = extract_cv_url(cv_field)
        assert result == "https://example.com/cv.pdf"


class TestParseCommaSeparated:
    """Tests for comma-separated field parsing."""

    def test_basic_parsing(self):
        """Test basic comma-separated parsing."""
        result = parse_comma_separated("Python,JavaScript,Rust")
        assert result == ["Python", "JavaScript", "Rust"]

    def test_handles_whitespace(self):
        """Test that whitespace around items is trimmed."""
        result = parse_comma_separated("Python , JavaScript , Rust")
        assert result == ["Python", "JavaScript", "Rust"]

    def test_filters_empty_items(self):
        """Test that empty items are filtered out."""
        result = parse_comma_separated("Python,,Rust,")
        assert result == ["Python", "Rust"]

    def test_returns_empty_for_none(self):
        """Test that None input returns empty list."""
        result = parse_comma_separated(None)
        assert result == []

    def test_returns_empty_for_empty_string(self):
        """Test that empty string returns empty list."""
        result = parse_comma_separated("")
        assert result == []


class TestMapAirtableRowToRawCandidate:
    """Tests for Airtable record mapping."""

    def test_maps_basic_fields(self):
        """Test that basic fields are mapped correctly."""
        record = {
            "id": "recXYZ123",
            "createdTime": "2024-01-15T10:30:00.000Z",
            "fields": {
                "Full Name": "John Doe",
                "Location": "San Francisco, CA",
                "Skills": "Python,Rust,Solana",
            },
        }
        
        result = map_airtable_row_to_raw_candidate(record)
        
        assert result["airtable_record_id"] == "recXYZ123"
        assert result["full_name"] == "John Doe"
        assert result["location_raw"] == "San Francisco, CA"
        assert result["skills_raw"] == "Python,Rust,Solana"
        assert result["source"] == "airtable"
        assert result["source_id"] == "recXYZ123"

    def test_maps_cv_url_from_attachment(self):
        """Test that CV URL is extracted from attachment format."""
        record = {
            "id": "recABC",
            "fields": {
                "Full Name": "Jane Doe",
                "CV": [{"url": "https://example.com/cv.pdf"}],
            },
        }
        
        result = map_airtable_row_to_raw_candidate(record)
        
        assert result["cv_url"] == "https://example.com/cv.pdf"

    def test_handles_missing_fields(self):
        """Test that missing fields are set to None."""
        record = {
            "id": "recMinimal",
            "fields": {
                "Full Name": "Minimal Candidate",
            },
        }
        
        result = map_airtable_row_to_raw_candidate(record)
        
        assert result["full_name"] == "Minimal Candidate"
        assert result["location_raw"] is None
        assert result["skills_raw"] is None
        assert result["cv_url"] is None
        assert result["linkedin_url"] is None

    def test_maps_all_profile_links(self):
        """Test that all profile links are mapped."""
        record = {
            "id": "recProfiles",
            "fields": {
                "Full Name": "Profile Person",
                "X Profile Link": "https://x.com/profile",
                "LinkedIn Profile": "https://linkedin.com/in/profile",
                "Git Hub Profile": "https://github.com/profile",
                "Earn Profile": "https://earn.superteam.fun/profile",
            },
        }
        
        result = map_airtable_row_to_raw_candidate(record)
        
        assert result["x_profile_url"] == "https://x.com/profile"
        assert result["linkedin_url"] == "https://linkedin.com/in/profile"
        assert result["github_url"] == "https://github.com/profile"
        assert result["earn_profile_url"] == "https://earn.superteam.fun/profile"


class TestAirtableResource:
    """Tests for the AirtableResource class."""

    @pytest.fixture
    def resource(self):
        """Create a test AirtableResource instance."""
        return AirtableResource(
            base_id="appTEST123456789",
            table_id="tblTEST123456789",
            api_key="pat_test_key",
        )

    def test_base_url_construction(self, resource):
        """Test that base URL is constructed correctly."""
        assert resource._base_url == "https://api.airtable.com/v0/appTEST123456789/tblTEST123456789"

    def test_headers_include_auth(self, resource):
        """Test that headers include authorization."""
        headers = resource._headers
        assert headers["Authorization"] == "Bearer pat_test_key"
        assert headers["Content-Type"] == "application/json"

    def test_record_hash_changes_on_content_change(self, resource):
        """Test that data version hash changes when content changes."""
        record1 = {
            "id": "rec1",
            "fields": {
                "Full Name": "John Doe",
                "Skills": "Python",
            },
        }
        record2 = {
            "id": "rec1",
            "fields": {
                "Full Name": "John Doe",
                "Skills": "Python,Rust",  # Changed
            },
        }
        
        mapped1 = resource._map_record(record1)
        mapped2 = resource._map_record(record2)
        
        assert mapped1["_data_version"] != mapped2["_data_version"]

    def test_record_hash_same_for_same_content(self, resource):
        """Test that data version hash is consistent for same content."""
        record = {
            "id": "rec1",
            "fields": {
                "Full Name": "John Doe",
                "Skills": "Python",
            },
        }
        
        mapped1 = resource._map_record(record)
        mapped2 = resource._map_record(record)
        
        assert mapped1["_data_version"] == mapped2["_data_version"]

    @patch("talent_matching.resources.airtable.httpx.Client")
    def test_fetch_record_by_id(self, mock_client_class, resource):
        """Test fetching a single record by ID."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "recTEST",
            "createdTime": "2024-01-15T10:30:00.000Z",
            "fields": {
                "Full Name": "Test User",
                "Skills": "Python,Rust",
            },
        }
        mock_client.get.return_value = mock_response
        
        result = resource.fetch_record_by_id("recTEST")
        
        assert result["airtable_record_id"] == "recTEST"
        assert result["full_name"] == "Test User"
        assert result["skills_raw"] == "Python,Rust"
        mock_client.get.assert_called_once()

    @patch("talent_matching.resources.airtable.httpx.Client")
    def test_fetch_all_records_handles_pagination(self, mock_client_class, resource):
        """Test that pagination is handled correctly."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
        
        # First page with offset
        page1_response = MagicMock()
        page1_response.json.return_value = {
            "records": [
                {"id": "rec1", "fields": {"Full Name": "User 1"}},
            ],
            "offset": "page2_cursor",
        }
        
        # Second page without offset (last page)
        page2_response = MagicMock()
        page2_response.json.return_value = {
            "records": [
                {"id": "rec2", "fields": {"Full Name": "User 2"}},
            ],
        }
        
        mock_client.get.side_effect = [page1_response, page2_response]
        
        result = resource.fetch_all_records()
        
        assert len(result) == 2
        assert result[0]["airtable_record_id"] == "rec1"
        assert result[1]["airtable_record_id"] == "rec2"
        assert mock_client.get.call_count == 2

    @patch("talent_matching.resources.airtable.httpx.Client")
    def test_get_all_record_ids(self, mock_client_class, resource):
        """Test getting all record IDs."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "records": [
                {"id": "rec1"},
                {"id": "rec2"},
                {"id": "rec3"},
            ],
        }
        mock_client.get.return_value = mock_response
        
        result = resource.get_all_record_ids()
        
        assert result == ["rec1", "rec2", "rec3"]
