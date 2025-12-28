from unittest.mock import AsyncMock, MagicMock


from bot.services.user_checker import ProfileCheckResult, check_user_profile


class TestProfileCheckResult:
    def test_is_complete_when_both_present(self):
        result = ProfileCheckResult(has_profile_photo=True, has_username=True)
        assert result.is_complete is True

    def test_is_not_complete_missing_photo(self):
        result = ProfileCheckResult(has_profile_photo=False, has_username=True)
        assert result.is_complete is False

    def test_is_not_complete_missing_username(self):
        result = ProfileCheckResult(has_profile_photo=True, has_username=False)
        assert result.is_complete is False

    def test_is_not_complete_missing_both(self):
        result = ProfileCheckResult(has_profile_photo=False, has_username=False)
        assert result.is_complete is False

    def test_get_missing_items_none(self):
        result = ProfileCheckResult(has_profile_photo=True, has_username=True)
        assert result.get_missing_items() == []

    def test_get_missing_items_photo_only(self):
        result = ProfileCheckResult(has_profile_photo=False, has_username=True)
        assert result.get_missing_items() == ["foto profil publik"]

    def test_get_missing_items_username_only(self):
        result = ProfileCheckResult(has_profile_photo=True, has_username=False)
        assert result.get_missing_items() == ["username"]

    def test_get_missing_items_both(self):
        result = ProfileCheckResult(has_profile_photo=False, has_username=False)
        assert result.get_missing_items() == ["foto profil publik", "username"]


class TestCheckUserProfile:
    async def test_user_with_photo_and_username(self):
        from bot.database.service import init_database, reset_database
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_database(str(db_path))

            bot = AsyncMock()
            user = MagicMock()
            user.id = 12345
            user.username = "testuser"

            photos = MagicMock()
            photos.total_count = 1
            bot.get_user_profile_photos.return_value = photos

            result = await check_user_profile(bot, user)

            assert result.has_profile_photo is True
            assert result.has_username is True
            assert result.is_complete is True
            bot.get_user_profile_photos.assert_called_once_with(12345, limit=1)

            reset_database()

    async def test_user_without_photo(self):
        from bot.database.service import init_database, reset_database
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_database(str(db_path))

            bot = AsyncMock()
            user = MagicMock()
            user.id = 12345
            user.username = "testuser"

            photos = MagicMock()
            photos.total_count = 0
            bot.get_user_profile_photos.return_value = photos

            result = await check_user_profile(bot, user)

            assert result.has_profile_photo is False
            assert result.has_username is True

            reset_database()

    async def test_user_without_username(self):
        from bot.database.service import init_database, reset_database
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_database(str(db_path))

            bot = AsyncMock()
            user = MagicMock()
            user.id = 12345
            user.username = None

            photos = MagicMock()
            photos.total_count = 3
            bot.get_user_profile_photos.return_value = photos

            result = await check_user_profile(bot, user)

            assert result.has_profile_photo is True
            assert result.has_username is False

            reset_database()

    async def test_user_without_both(self):
        from bot.database.service import init_database, reset_database
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_database(str(db_path))

            bot = AsyncMock()
            user = MagicMock()
            user.id = 12345
            user.username = None

            photos = MagicMock()
            photos.total_count = 0
            bot.get_user_profile_photos.return_value = photos

            result = await check_user_profile(bot, user)

            assert result.has_profile_photo is False
            assert result.has_username is False
            assert result.is_complete is False

            reset_database()

    async def test_whitelisted_user_skips_api_check(self):
        from bot.database.service import get_database, init_database, reset_database
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_database(str(db_path))

            db = get_database()
            db.add_photo_verification_whitelist(user_id=12345, verified_by_admin_id=99999)

            bot = AsyncMock()
            user = MagicMock()
            user.id = 12345
            user.username = "testuser"

            result = await check_user_profile(bot, user)

            assert result.has_profile_photo is True
            assert result.has_username is True
            assert result.is_complete is True
            bot.get_user_profile_photos.assert_not_called()

            reset_database()


class TestCheckUserProfileErrorHandling:
    async def test_get_profile_photos_exception_logged_and_raised(self):
        """Test when bot.get_user_profile_photos() raises an exception (lines 88-90)."""
        from bot.database.service import init_database, reset_database
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_database(str(db_path))

            bot = AsyncMock()
            user = MagicMock()
            user.id = 12345
            user.username = "testuser"

            bot.get_user_profile_photos.side_effect = Exception("test error")

            import pytest
            with pytest.raises(Exception, match="test error"):
                await check_user_profile(bot, user)

            bot.get_user_profile_photos.assert_called_once_with(12345, limit=1)

            reset_database()
