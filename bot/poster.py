import logging
from typing import Iterable, List, Optional

from mastodon import Mastodon

logger = logging.getLogger(__name__)


class MastodonPoster:
    def __init__(self, access_token: str, base_url: str, character_limit: int = 500):
        self.client = Mastodon(access_token=access_token, api_base_url=base_url)
        self.character_limit = character_limit

    def post_thread(self, posts: Iterable[str]) -> Optional[List[dict]]:
        reply_to = None
        results = []
        for content in posts:
            if len(content) > self.character_limit:
                logger.warning("Post exceeds character limit (%s): truncating", self.character_limit)
                content = content[: self.character_limit]
            status = self.client.status_post(content, in_reply_to_id=reply_to, visibility="public")
            reply_to = status["id"]
            results.append(status)
        return results
