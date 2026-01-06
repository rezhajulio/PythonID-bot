from unittest.mock import MagicMock

from telegram import Message, MessageEntity

from bot.handlers.anti_spam import (
    extract_urls,
    has_external_reply,
    has_link,
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


# Tests for has_link
def test_has_link_with_url_entity():
    """Test has_link detects URL entities."""
    message = MagicMock(spec=Message)
    entity = MagicMock(spec=MessageEntity)
    entity.type = MessageEntity.URL
    message.entities = [entity]
    message.caption_entities = None
    assert has_link(message)


def test_has_link_with_text_link_entity():
    """Test has_link detects TEXT_LINK entities."""
    message = MagicMock(spec=Message)
    entity = MagicMock(spec=MessageEntity)
    entity.type = MessageEntity.TEXT_LINK
    message.entities = [entity]
    message.caption_entities = None
    assert has_link(message)


def test_has_link_in_caption_entities():
    """Test has_link detects links in caption entities."""
    message = MagicMock(spec=Message)
    entity = MagicMock(spec=MessageEntity)
    entity.type = MessageEntity.URL
    message.entities = None
    message.caption_entities = [entity]
    assert has_link(message)


def test_has_link_with_multiple_entities():
    """Test has_link works with multiple entities."""
    message = MagicMock(spec=Message)
    url_entity = MagicMock(spec=MessageEntity)
    url_entity.type = MessageEntity.URL
    bold_entity = MagicMock(spec=MessageEntity)
    bold_entity.type = MessageEntity.BOLD
    message.entities = [bold_entity, url_entity]
    message.caption_entities = None
    assert has_link(message)


def test_has_link_no_link_entities():
    """Test has_link returns False when no link entities exist."""
    message = MagicMock(spec=Message)
    entity = MagicMock(spec=MessageEntity)
    entity.type = MessageEntity.BOLD
    message.entities = [entity]
    message.caption_entities = None
    assert not has_link(message)


def test_has_link_empty_entities():
    """Test has_link returns False for messages without entities."""
    message = MagicMock(spec=Message)
    message.entities = None
    message.caption_entities = None
    assert not has_link(message)


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
def test_extract_urls_with_url_entities():
    """Test extract_urls extracts inline URLs."""
    message = MagicMock(spec=Message)
    entity = MagicMock(spec=MessageEntity)
    entity.type = MessageEntity.URL
    entity.offset = 0
    entity.length = 19
    message.entities = [entity]
    message.caption_entities = None
    message.text = "https://github.com/"
    message.caption = None
    assert extract_urls(message) == ["https://github.com/"]


def test_extract_urls_with_text_link_entities():
    """Test extract_urls extracts TEXT_LINK URLs."""
    message = MagicMock(spec=Message)
    entity = MagicMock(spec=MessageEntity)
    entity.type = MessageEntity.TEXT_LINK
    entity.url = "https://github.com/user/repo"
    message.entities = [entity]
    message.caption_entities = None
    message.text = "Click here"
    message.caption = None
    assert extract_urls(message) == ["https://github.com/user/repo"]


def test_extract_urls_from_caption():
    """Test extract_urls extracts URLs from caption entities."""
    message = MagicMock(spec=Message)
    entity = MagicMock(spec=MessageEntity)
    entity.type = MessageEntity.URL
    entity.offset = 0
    entity.length = 11
    message.entities = None
    message.caption_entities = [entity]
    message.text = None
    message.caption = "github.com/"
    assert extract_urls(message) == ["github.com/"]


def test_extract_urls_mixed_entities():
    """Test extract_urls with mixed URL and non-URL entities."""
    message = MagicMock(spec=Message)
    url_entity = MagicMock(spec=MessageEntity)
    url_entity.type = MessageEntity.URL
    url_entity.offset = 0
    url_entity.length = 19
    bold_entity = MagicMock(spec=MessageEntity)
    bold_entity.type = MessageEntity.BOLD
    message.entities = [url_entity, bold_entity]
    message.caption_entities = None
    message.text = "https://github.com/"
    message.caption = None
    assert extract_urls(message) == ["https://github.com/"]


def test_extract_urls_no_entities():
    """Test extract_urls returns empty list for messages without URLs."""
    message = MagicMock(spec=Message)
    message.entities = None
    message.caption_entities = None
    message.text = "No URLs here"
    message.caption = None
    assert extract_urls(message) == []


def test_extract_urls_multiple_urls():
    """Test extract_urls extracts multiple URLs."""
    message = MagicMock(spec=Message)
    entity1 = MagicMock(spec=MessageEntity)
    entity1.type = MessageEntity.URL
    entity1.offset = 0
    entity1.length = 19
    entity2 = MagicMock(spec=MessageEntity)
    entity2.type = MessageEntity.URL
    entity2.offset = 20
    entity2.length = 19
    message.entities = [entity1, entity2]
    message.caption_entities = None
    message.text = "https://github.com/ https://google.com/"
    message.caption = None
    urls = extract_urls(message)
    assert len(urls) == 2
    assert "https://github.com/" in urls
    assert "https://google.com/" in urls


# Tests for has_non_whitelisted_link
def test_has_non_whitelisted_link_with_whitelisted():
    """Test has_non_whitelisted_link returns False for whitelisted URLs."""
    message = MagicMock(spec=Message)
    entity = MagicMock(spec=MessageEntity)
    entity.type = MessageEntity.URL
    entity.offset = 0
    entity.length = 19
    message.entities = [entity]
    message.caption_entities = None
    message.text = "https://github.com/"
    message.caption = None
    assert not has_non_whitelisted_link(message)


def test_has_non_whitelisted_link_with_non_whitelisted():
    """Test has_non_whitelisted_link returns True for non-whitelisted URLs."""
    message = MagicMock(spec=Message)
    entity = MagicMock(spec=MessageEntity)
    entity.type = MessageEntity.URL
    entity.offset = 0
    entity.length = 18
    message.entities = [entity]
    message.caption_entities = None
    message.text = "https://google.com/"
    message.caption = None
    assert has_non_whitelisted_link(message)


def test_has_non_whitelisted_link_mixed_urls():
    """Test has_non_whitelisted_link with mix of whitelisted and non-whitelisted."""
    message = MagicMock(spec=Message)
    entity1 = MagicMock(spec=MessageEntity)
    entity1.type = MessageEntity.URL
    entity1.offset = 0
    entity1.length = 19
    entity2 = MagicMock(spec=MessageEntity)
    entity2.type = MessageEntity.URL
    entity2.offset = 20
    entity2.length = 18
    message.entities = [entity1, entity2]
    message.caption_entities = None
    message.text = "https://github.com/ https://google.com/"
    message.caption = None
    assert has_non_whitelisted_link(message)


def test_has_non_whitelisted_link_no_urls():
    """Test has_non_whitelisted_link returns False for messages without URLs."""
    message = MagicMock(spec=Message)
    message.entities = None
    message.caption_entities = None
    message.text = "No URLs here"
    message.caption = None
    assert not has_non_whitelisted_link(message)

