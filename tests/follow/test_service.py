"""Direct service-level unit tests for app/follow/service.py.

API-level coverage lives in tests/follow/test_views.py; the unverified-user
gating flow is covered by tests/integration/test_email_verification.py.
"""

from app.follow import service


class TestIsFollowing:
    def test_false_when_no_relation(self, db_session, create_user):
        alice = create_user(username="alice_isf")
        bob = create_user(username="bob_isf")
        assert service.is_following(alice.id, bob.id, db_session) is False

    def test_true_after_follow(self, db_session, create_user):
        alice = create_user(username="alice_isf2")
        bob = create_user(username="bob_isf2")
        alice.followed.append(bob)
        db_session.commit()
        assert service.is_following(alice.id, bob.id, db_session) is True

    def test_asymmetric(self, db_session, create_user):
        """Following is directional: A→B does not imply B→A."""
        alice = create_user(username="alice_asym")
        bob = create_user(username="bob_asym")
        alice.followed.append(bob)
        db_session.commit()
        assert service.is_following(alice.id, bob.id, db_session) is True
        assert service.is_following(bob.id, alice.id, db_session) is False


class TestFollowUser:
    def test_persists_edge(self, db_session, create_user):
        alice = create_user(username="alice_fu")
        bob = create_user(username="bob_fu")
        service.follow_user(alice, bob, db_session)
        db_session.refresh(alice)
        assert bob in alice.followed

    def test_appears_in_is_following(self, db_session, create_user):
        alice = create_user(username="alice_appear")
        bob = create_user(username="bob_appear")
        service.follow_user(alice, bob, db_session)
        assert service.is_following(alice.id, bob.id, db_session) is True


class TestUnfollowUser:
    def test_removes_edge(self, db_session, create_user):
        alice = create_user(username="alice_uf")
        bob = create_user(username="bob_uf")
        service.follow_user(alice, bob, db_session)
        service.unfollow_user(alice, bob, db_session)
        db_session.refresh(alice)
        assert bob not in alice.followed
        assert service.is_following(alice.id, bob.id, db_session) is False

    def test_multiple_follows_and_selective_unfollow(self, db_session, create_user):
        alice = create_user(username="alice_multi")
        bob = create_user(username="bob_multi")
        carol = create_user(username="carol_multi")
        service.follow_user(alice, bob, db_session)
        service.follow_user(alice, carol, db_session)
        service.unfollow_user(alice, bob, db_session)
        db_session.refresh(alice)
        assert bob not in alice.followed
        assert carol in alice.followed
