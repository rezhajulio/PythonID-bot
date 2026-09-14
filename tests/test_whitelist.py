from unittest.mock import MagicMock

from telegram import Message, MessageEntity

from bot.handlers.anti_spam import (
    extract_urls,
    has_external_reply,
    has_non_whitelisted_link,
    has_story,
    is_forwarded,
    is_url_whitelisted,
)


def test_telegram_whitelist_allowed_internal_links():
    """Test allowed Telegram links with different protocols."""
    assert is_url_whitelisted("https://t.me/PythonID")
    assert is_url_whitelisted("http://t.me/PythonID")
    assert is_url_whitelisted("t.me/PythonID")
    assert is_url_whitelisted("https://telegram.me/PythonID")


def test_telegram_whitelist_message_links():
    """Test Telegram message links (with message IDs)."""
    assert is_url_whitelisted("https://t.me/pythonid/12345")
    assert is_url_whitelisted("https://t.me/JuaraGCP/999")
    assert is_url_whitelisted("t.me/awsdatausergroupid/456")


def test_telegram_whitelist_friend_communities():
    """Test allowed friend community links."""
    assert is_url_whitelisted("https://t.me/JuaraGCP")
    assert is_url_whitelisted("https://t.me/AWSDataUserGroupID")
    assert is_url_whitelisted("https://t.me/awsusergroupid")
    assert is_url_whitelisted("https://t.me/DataScienceIndonesia")


def test_telegram_whitelist_case_insensitive():
    """Test that Telegram path matching is case-insensitive."""
    assert is_url_whitelisted("https://t.me/PYTHONID")
    assert is_url_whitelisted("https://t.me/pythonid")
    assert is_url_whitelisted("https://t.me/PyThOnId")
    assert is_url_whitelisted("https://t.me/JUARAGCP")
    assert is_url_whitelisted("https://t.me/juaragcp")


def test_telegram_whitelist_disallowed_links():
    """Test that non-whitelisted Telegram links are rejected."""
    assert not is_url_whitelisted("https://t.me/SpamGroup")
    assert not is_url_whitelisted("https://t.me/CryptoScam")
    assert not is_url_whitelisted("https://t.me/RandomChannel")
    assert not is_url_whitelisted("https://t.me/FakeNews")


def test_telegram_whitelist_root_path():
    """Test that Telegram root path is rejected."""
    assert not is_url_whitelisted("https://t.me/")
    assert not is_url_whitelisted("t.me/")
    assert not is_url_whitelisted("https://telegram.me/")


def test_telegram_whitelist_with_port():
    """Test Telegram links with port numbers."""
    assert is_url_whitelisted("https://t.me:443/PythonID")
    assert is_url_whitelisted("https://t.me:8080/juaragcp")
    assert not is_url_whitelisted("https://t.me:443/SpamGroup")


def test_url_userinfo_injection_bypass():
    """Regression: URLs with userinfo must NOT match whitelisted domains."""
    assert not is_url_whitelisted("https://docs.python.org:secret@malicious.com/scam")
    assert not is_url_whitelisted("https://github.com:x@evil.com/phish")
    assert not is_url_whitelisted("https://user:pass@github.com/repo")
    assert not is_url_whitelisted("https://t.me:foo@evil.com/pythonid")
    assert not is_url_whitelisted("https://user@t.me/pythonid")


def test_telegram_path_traversal_bypass():
    """Regression: path traversal must NOT trick the first-segment check."""
    assert not is_url_whitelisted("https://t.me/pythonid/../../scam_group")
    assert not is_url_whitelisted("https://t.me/juaragcp/../scam")
    assert not is_url_whitelisted("https://t.me/pythonid/./../../evil")
    # Reverse direction: erasing a non-whitelisted segment must not promote
    # a whitelisted one that only appears after the traversal.
    assert not is_url_whitelisted("https://t.me/scam_group/../pythonid")
    assert not is_url_whitelisted("https://t.me/freemoney/../juaragcp")
    assert not is_url_whitelisted("https://t.me/../pythonid")
    assert not is_url_whitelisted("https://t.me/a/b/../../pythonid")


def test_domain_whitelist_github():
    """Test GitHub domain whitelisting."""
    assert is_url_whitelisted("https://github.com/rezhajulio/PythonID-bot")
    assert is_url_whitelisted("http://github.com/user/repo")
    assert is_url_whitelisted("github.com/user/repo")
    assert is_url_whitelisted("https://gist.github.com/user/id")
    assert is_url_whitelisted("https://raw.githubusercontent.com/user/repo/main/file.txt")


def test_domain_whitelist_subdomains():
    """Test that subdomains of whitelisted domains are allowed."""
    assert is_url_whitelisted("https://docs.python.org")
    assert is_url_whitelisted("https://subdomain.docs.python.org")
    assert is_url_whitelisted("https://another.sub.docs.python.org")
    assert is_url_whitelisted("https://docs.sqlalchemy.org")


def test_domain_whitelist_documentation():
    """Test various documentation domains."""
    assert is_url_whitelisted("https://docs.djangoproject.com")
    assert is_url_whitelisted("https://flask.palletsprojects.com")
    assert is_url_whitelisted("https://fastapi.tiangolo.com")
    assert is_url_whitelisted("https://pydantic.dev")
    assert is_url_whitelisted("https://docs.sqlalchemy.org")
    assert is_url_whitelisted("https://pandas.pydata.org")
    assert is_url_whitelisted("https://numpy.org")
    assert is_url_whitelisted("https://scipy.org")
    assert is_url_whitelisted("https://matplotlib.org")
    assert is_url_whitelisted("https://scikit-learn.org")


def test_domain_whitelist_ai_ml_platforms():
    """Test AI/ML platform domains."""
    assert is_url_whitelisted("https://pytorch.org")
    assert is_url_whitelisted("https://tensorflow.org")
    assert is_url_whitelisted("https://keras.io")
    assert is_url_whitelisted("https://huggingface.co")
    assert is_url_whitelisted("https://openai.com")
    assert is_url_whitelisted("https://anthropic.com")
    assert is_url_whitelisted("https://langchain.com")


def test_domain_whitelist_cloud_providers():
    """Test cloud provider domains."""
    assert is_url_whitelisted("https://docs.aws.amazon.com")
    assert is_url_whitelisted("https://cloud.google.com")
    assert is_url_whitelisted("https://docs.microsoft.com")
    assert is_url_whitelisted("https://learn.microsoft.com")


def test_domain_whitelist_code_hosting():
    """Test code hosting platforms."""
    assert is_url_whitelisted("https://gitlab.com/user/project")
    assert is_url_whitelisted("https://bitbucket.org/user/repo")


def test_domain_whitelist_package_repositories():
    """Test package repository domains."""
    assert is_url_whitelisted("https://pypi.org/project/django")
    assert is_url_whitelisted("https://anaconda.org/conda-forge/numpy")
    assert is_url_whitelisted("https://conda.io/projects/conda")
    assert is_url_whitelisted("https://hub.docker.com/r/python")


def test_domain_whitelist_community_learning():
    """Test community and learning platforms."""
    assert is_url_whitelisted("https://stackoverflow.com/questions/123")
    assert is_url_whitelisted("https://stackexchange.com")
    assert is_url_whitelisted("https://reddit.com/r/Python")
    assert is_url_whitelisted("https://medium.com/@author/article")
    assert is_url_whitelisted("https://towardsdatascience.com/article")
    assert is_url_whitelisted("https://dev.to/author/post")
    assert is_url_whitelisted("https://realpython.com/tutorial")
    assert is_url_whitelisted("https://pythonweekly.com")
    assert is_url_whitelisted("https://kaggle.com/datasets")
    assert is_url_whitelisted("https://colab.research.google.com")


def test_domain_whitelist_data_science():
    """Test data science and ML resource domains."""
    assert is_url_whitelisted("https://arxiv.org/abs/2112.00000")
    assert is_url_whitelisted("https://paperswithcode.com/paper/some-paper")
    assert is_url_whitelisted("https://wandb.ai/project")
    assert is_url_whitelisted("https://mlflow.org")
    assert is_url_whitelisted("https://streamlit.io")
    assert is_url_whitelisted("https://gradio.app")
    assert is_url_whitelisted("https://jupyter.org")
    assert is_url_whitelisted("https://nbviewer.jupyter.org/github/user/repo")


def test_domain_whitelist_api_docs():
    """Test API documentation domains."""
    assert is_url_whitelisted("https://developers.google.com")
    assert is_url_whitelisted("https://developer.twitter.com/en/docs")
    assert is_url_whitelisted("https://developer.github.com")
    assert is_url_whitelisted("https://api.telegram.org")
    assert is_url_whitelisted("https://core.telegram.org")


def test_domain_whitelist_indonesian_communities():
    """Test Indonesian tech community domains."""
    assert is_url_whitelisted("https://dicoding.com/learning/path")


def test_non_whitelisted_domains():
    """Test that non-whitelisted domains are rejected."""
    assert not is_url_whitelisted("https://google.com")
    assert not is_url_whitelisted("https://facebook.com")
    assert not is_url_whitelisted("https://twitter.com")
    assert not is_url_whitelisted("https://random-spam-site.com")
    assert not is_url_whitelisted("https://unknown-domain.org")
    assert not is_url_whitelisted("http://malicious.net")


def test_url_without_scheme():
    """Test URLs without http/https schemes are automatically prefixed."""
    assert is_url_whitelisted("github.com/user/repo")
    assert is_url_whitelisted("docs.python.org")
    assert is_url_whitelisted("t.me/PythonID")
    assert not is_url_whitelisted("google.com")


def test_url_with_query_parameters():
    """Test URLs with query parameters."""
    assert is_url_whitelisted("https://github.com/user/repo?tab=readme")
    assert is_url_whitelisted("https://docs.python.org/3/library/os.html?highlight=path")
    assert not is_url_whitelisted("https://google.com/search?q=spam")


def test_url_with_fragments():
    """Test URLs with URL fragments."""
    assert is_url_whitelisted("https://github.com/user/repo#section")
    assert is_url_whitelisted("https://docs.python.org/3/library/os.html#os.path.join")
    assert not is_url_whitelisted("https://google.com#top")


def test_url_with_userinfo():
    """Test URLs with user info (credentials in URL) - unsupported format."""
    # Note: URLs with embedded credentials may not parse correctly with urlparse
    # in some cases, so we test edge cases that actually work
    assert not is_url_whitelisted("https://user:pass@google.com")


def test_malformed_urls():
    """Test that malformed URLs are gracefully handled."""
    assert not is_url_whitelisted("not a url at all")
    assert not is_url_whitelisted("://missing-protocol")
    assert not is_url_whitelisted("")
    assert not is_url_whitelisted(" ")


def test_special_characters_in_url():
    """Test URLs with special characters."""
    assert is_url_whitelisted("https://github.com/user-name/repo-name")
    assert is_url_whitelisted("https://docs.python.org/3/library/file.html")
    # Telegram paths with underscores must be whitelisted usernames
    assert is_url_whitelisted("https://t.me/bandungdevcom")


def test_url_case_sensitivity():
    """Test that domain matching is case-insensitive."""
    assert is_url_whitelisted("https://GITHUB.COM/user/repo")
    assert is_url_whitelisted("https://GitHub.com/user/repo")
    assert is_url_whitelisted("https://DOCS.PYTHON.ORG")
    assert is_url_whitelisted("https://Docs.Python.Org")


# Tests for is_forwarded
def test_is_forwarded_with_forward_origin():
    """Test is_forwarded detects messages with forward_origin."""
    message = MagicMock(spec=Message)
    message.forward_origin = MagicMock()
    assert is_forwarded(message)


def test_is_forwarded_without_forward_origin():
    """Test is_forwarded returns False for normal messages."""
    message = MagicMock(spec=Message)
    message.forward_origin = None
    assert not is_forwarded(message)


# Tests for has_external_reply
def test_has_external_reply_with_external_reply():
    """Test has_external_reply detects external replies."""
    message = MagicMock(spec=Message)
    message.external_reply = MagicMock()
    assert has_external_reply(message)


def test_has_external_reply_without_external_reply():
    """Test has_external_reply returns False for normal messages."""
    message = MagicMock(spec=Message)
    message.external_reply = None
    assert not has_external_reply(message)


# Tests for has_story
def test_has_story_with_story():
    """Test has_story detects forwarded stories."""
    message = MagicMock(spec=Message)
    message.story = MagicMock()
    assert has_story(message)


def test_has_story_without_story():
    """Test has_story returns False for messages without stories."""
    message = MagicMock(spec=Message)
    message.story = None
    assert not has_story(message)


# Tests for extract_urls
def _make_message(text=None, caption=None, entities=None, caption_entities=None):
    """Build a real telegram.Message so UTF-16 offsets and entity filtering
    are exercised for real, instead of stubbing parse_entities/parse_caption_entities."""
    from datetime import UTC, datetime

    from telegram import Chat

    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=1, type="private"),
        text=text,
        caption=caption,
        entities=entities,
        caption_entities=caption_entities,
    )


def test_extract_urls_with_url_entities():
    """Test extract_urls extracts inline URLs."""
    url = "https://github.com/"
    message = _make_message(
        text=url, entities=[MessageEntity(type=MessageEntity.URL, offset=0, length=len(url))]
    )
    assert extract_urls(message) == [url]


def test_extract_urls_with_text_link_entities():
    """Test extract_urls extracts TEXT_LINK URLs."""
    message = _make_message(
        text="Click here",
        entities=[
            MessageEntity(
                type=MessageEntity.TEXT_LINK,
                offset=0,
                length=10,
                url="https://github.com/user/repo",
            )
        ],
    )
    assert extract_urls(message) == ["https://github.com/user/repo"]


def test_extract_urls_from_caption():
    """Test extract_urls extracts URLs from caption entities."""
    caption = "github.com/"
    message = _make_message(
        caption=caption,
        caption_entities=[MessageEntity(type=MessageEntity.URL, offset=0, length=len(caption))],
    )
    assert extract_urls(message) == [caption]


def test_extract_urls_mixed_entities():
    """Test extract_urls with mixed URL and non-URL entities; the BOLD
    entity must be excluded by the [MessageEntity.URL] filter, not just
    happen to be absent from a stubbed return value."""
    url = "https://github.com/"
    text = f"{url} bold"
    message = _make_message(
        text=text,
        entities=[
            MessageEntity(type=MessageEntity.URL, offset=0, length=len(url)),
            MessageEntity(type=MessageEntity.BOLD, offset=len(url) + 1, length=4),
        ],
    )
    assert extract_urls(message) == [url]


def test_extract_urls_no_entities():
    """Test extract_urls returns empty list for messages without URLs."""
    message = _make_message(text="No URLs here")
    assert extract_urls(message) == []


def test_extract_urls_multiple_urls():
    """Test extract_urls extracts multiple URLs, sliced from real offsets."""
    url1, url2 = "https://github.com/", "https://google.com/"
    text = f"{url1} {url2}"
    message = _make_message(
        text=text,
        entities=[
            MessageEntity(type=MessageEntity.URL, offset=0, length=len(url1)),
            MessageEntity(type=MessageEntity.URL, offset=len(url1) + 1, length=len(url2)),
        ],
    )
    urls = extract_urls(message)
    assert len(urls) == 2
    assert url1 in urls
    assert url2 in urls


# Tests for has_non_whitelisted_link
def test_has_non_whitelisted_link_with_whitelisted():
    """Test has_non_whitelisted_link returns False for whitelisted URLs."""
    url = "https://github.com/"
    message = _make_message(
        text=url, entities=[MessageEntity(type=MessageEntity.URL, offset=0, length=len(url))]
    )
    assert not has_non_whitelisted_link(message)


def test_has_non_whitelisted_link_with_non_whitelisted():
    """Test has_non_whitelisted_link returns True for non-whitelisted URLs."""
    url = "https://malicious-site.com/"
    message = _make_message(
        text=url, entities=[MessageEntity(type=MessageEntity.URL, offset=0, length=len(url))]
    )
    assert has_non_whitelisted_link(message)


def test_has_non_whitelisted_link_mixed_urls():
    """Test has_non_whitelisted_link with mix of whitelisted and non-whitelisted."""
    url1, url2 = "https://github.com/", "https://malicious-site.com/"
    text = f"{url1} {url2}"
    message = _make_message(
        text=text,
        entities=[
            MessageEntity(type=MessageEntity.URL, offset=0, length=len(url1)),
            MessageEntity(type=MessageEntity.URL, offset=len(url1) + 1, length=len(url2)),
        ],
    )
    assert has_non_whitelisted_link(message)


def test_has_non_whitelisted_link_no_urls():
    """Test has_non_whitelisted_link returns False for messages without URLs."""
    message = _make_message(text="No URLs here")
    assert not has_non_whitelisted_link(message)
