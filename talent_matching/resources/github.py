"""GitHub API resource for fetching developer activity metrics.

This module provides both a mock implementation for testing and a stub
for the future production implementation.
"""

import random
from datetime import datetime, timedelta
from typing import Any

from dagster import ConfigurableResource
from pydantic import Field


class GitHubAPIResource(ConfigurableResource):
    """GitHub API resource for fetching developer statistics.
    
    In production, this would use the GitHub API with proper authentication.
    Currently implemented as a mock that returns plausible test data.
    """

    api_token: str = Field(
        default="",
        description="GitHub API token (leave empty for mock mode)",
    )
    mock_mode: bool = Field(
        default=True,
        description="If True, return mock data instead of calling GitHub API",
    )

    def get_user_stats(self, username: str) -> dict[str, Any]:
        """Fetch GitHub statistics for a user.
        
        Args:
            username: GitHub username
            
        Returns:
            Dictionary containing GitHub activity metrics
        """
        if self.mock_mode or not self.api_token:
            return self._mock_user_stats(username)
        
        # Production implementation would go here
        # For now, always use mock
        return self._mock_user_stats(username)

    def _mock_user_stats(self, username: str) -> dict[str, Any]:
        """Generate mock GitHub statistics.
        
        Uses username hash for deterministic results.
        """
        # Use username for deterministic mock data
        seed = hash(username) % (2**32)
        rng = random.Random(seed)
        
        # Calculate account age
        years_active = rng.randint(1, 10)
        account_created = datetime.now() - timedelta(days=years_active * 365)
        
        # Generate language distribution
        all_languages = ["Python", "JavaScript", "TypeScript", "Rust", "Go", "Solidity", "Java", "C++"]
        num_languages = rng.randint(2, 6)
        languages = rng.sample(all_languages, num_languages)
        
        # Generate contribution pattern
        total_commits = rng.randint(100, 5000)
        total_repos = rng.randint(5, 100)
        total_stars = rng.randint(0, 500)
        
        # Consistency score based on activity patterns
        # 1-5 scale: 1=sporadic, 5=very consistent
        consistency_score = rng.randint(1, 5)
        
        return {
            "username": username,
            "github_commits": total_commits,
            "github_repos": total_repos,
            "github_stars": total_stars,
            "github_years_active": years_active,
            "github_languages": languages,
            "github_consistency_score": consistency_score,
            "account_created": account_created.isoformat(),
            "followers": rng.randint(0, 1000),
            "following": rng.randint(0, 500),
            "public_gists": rng.randint(0, 50),
            "contributions_last_year": rng.randint(50, 1000),
            "_meta": {
                "fetched_at": datetime.now().isoformat(),
                "mock": True,
            },
        }

    def get_repo_stats(self, owner: str, repo: str) -> dict[str, Any]:
        """Fetch statistics for a specific repository.
        
        Args:
            owner: Repository owner username
            repo: Repository name
            
        Returns:
            Dictionary containing repository metrics
        """
        if self.mock_mode or not self.api_token:
            return self._mock_repo_stats(owner, repo)
        
        return self._mock_repo_stats(owner, repo)

    def _mock_repo_stats(self, owner: str, repo: str) -> dict[str, Any]:
        """Generate mock repository statistics."""
        seed = hash(f"{owner}/{repo}") % (2**32)
        rng = random.Random(seed)
        
        languages = ["Python", "JavaScript", "TypeScript", "Rust"]
        
        return {
            "owner": owner,
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "stars": rng.randint(0, 1000),
            "forks": rng.randint(0, 200),
            "watchers": rng.randint(0, 100),
            "open_issues": rng.randint(0, 50),
            "primary_language": rng.choice(languages),
            "languages": rng.sample(languages, k=rng.randint(1, 3)),
            "created_at": (datetime.now() - timedelta(days=rng.randint(30, 1000))).isoformat(),
            "updated_at": (datetime.now() - timedelta(days=rng.randint(0, 30))).isoformat(),
            "description": f"A mock repository for {repo}",
            "_meta": {
                "fetched_at": datetime.now().isoformat(),
                "mock": True,
            },
        }

    def check_rate_limit(self) -> dict[str, Any]:
        """Check current GitHub API rate limit status.
        
        Returns:
            Dictionary with rate limit information
        """
        if self.mock_mode or not self.api_token:
            return {
                "limit": 5000,
                "remaining": 4999,
                "reset_at": (datetime.now() + timedelta(hours=1)).isoformat(),
                "mock": True,
            }
        
        # Production implementation would check actual rate limits
        return {
            "limit": 5000,
            "remaining": 4999,
            "reset_at": (datetime.now() + timedelta(hours=1)).isoformat(),
            "mock": True,
        }
