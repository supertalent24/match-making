"""Tests for Dagster resources."""

from talent_matching.resources import (
    GitHubAPIResource,
    MockEmbeddingResource,
    MockLLMResource,
)


class TestMockLLMResource:
    """Tests for the MockLLMResource."""

    def test_normalize_cv_returns_structured_data(self):
        """Test that CV normalization returns expected structure."""
        resource = MockLLMResource()
        result = resource.normalize_cv("John Doe - Software Engineer...")
        
        assert "name" in result
        assert "years_of_experience" in result
        assert "skills" in result
        assert "experience" in result
        assert "_meta" in result
        assert result["_meta"]["model_version"] == "mock-v1"

    def test_normalize_job_returns_structured_data(self):
        """Test that job normalization returns expected structure."""
        resource = MockLLMResource()
        result = resource.normalize_job("Looking for a Senior Engineer...")
        
        assert "title" in result
        assert "seniority_level" in result
        assert "requirements" in result
        assert "must_have_skills" in result["requirements"]
        assert "_meta" in result

    def test_score_candidate_returns_scores(self):
        """Test that candidate scoring returns expected structure."""
        resource = MockLLMResource()
        profile = {"name": "Test", "skills": ["Python"]}
        result = resource.score_candidate(profile)
        
        assert "overall_score" in result
        assert 0 <= result["overall_score"] <= 1
        assert "experience_score" in result
        assert "skills_score" in result


class TestMockEmbeddingResource:
    """Tests for the MockEmbeddingResource."""

    def test_embed_returns_correct_dimensions(self):
        """Test that embeddings have correct dimensions."""
        resource = MockEmbeddingResource(dimensions=1536)
        result = resource.embed("Test text")
        
        assert len(result) == 1536
        assert all(isinstance(x, float) for x in result)

    def test_embed_is_normalized(self):
        """Test that embeddings are unit normalized."""
        resource = MockEmbeddingResource()
        result = resource.embed("Test text")
        
        # Check that magnitude is ~1.0 (unit vector)
        magnitude = sum(x * x for x in result) ** 0.5
        assert abs(magnitude - 1.0) < 0.0001

    def test_deterministic_mode_gives_same_results(self):
        """Test that deterministic mode produces consistent results."""
        resource = MockEmbeddingResource(deterministic=True)
        
        result1 = resource.embed("Same text")
        result2 = resource.embed("Same text")
        
        assert result1 == result2

    def test_embed_batch_returns_multiple_vectors(self):
        """Test batch embedding."""
        resource = MockEmbeddingResource()
        texts = ["Text 1", "Text 2", "Text 3"]
        result = resource.embed_batch(texts)
        
        assert len(result) == 3
        assert all(len(v) == 1536 for v in result)


class TestGitHubAPIResource:
    """Tests for the GitHubAPIResource."""

    def test_mock_mode_returns_data(self):
        """Test that mock mode returns plausible data."""
        resource = GitHubAPIResource(mock_mode=True)
        result = resource.get_user_stats("testuser")
        
        assert result["username"] == "testuser"
        assert "github_commits" in result
        assert "github_repos" in result
        assert "github_languages" in result
        assert result["_meta"]["mock"] is True

    def test_deterministic_mock_data(self):
        """Test that same username gives same mock data."""
        resource = GitHubAPIResource(mock_mode=True)
        
        result1 = resource.get_user_stats("consistent_user")
        result2 = resource.get_user_stats("consistent_user")
        
        assert result1["github_commits"] == result2["github_commits"]
        assert result1["github_repos"] == result2["github_repos"]

    def test_rate_limit_check(self):
        """Test rate limit checking."""
        resource = GitHubAPIResource(mock_mode=True)
        result = resource.check_rate_limit()
        
        assert "limit" in result
        assert "remaining" in result
        assert result["mock"] is True
