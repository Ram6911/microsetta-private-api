import unittest
import uuid

from microsetta_private_api.model.interested_user import InterestedUser
from microsetta_private_api.repo.interested_user_repo import InterestedUserRepo
from microsetta_private_api.repo.transaction import Transaction
from psycopg2.errors import ForeignKeyViolation


class InterestedUserRepoTests(unittest.TestCase):
    def setUp(self):
        self.test_campaign_title_1 = 'Test Campaign'
        with Transaction() as t:
            cur = t.cursor()

            # create a test campaign
            cur.execute(
                "INSERT INTO barcodes.campaigns (title) "
                "VALUES (%s) "
                "RETURNING campaign_id",
                (self.test_campaign_title_1, )
            )
            self.test_campaign_id = cur.fetchone()[0]

            # create necessary campaign/project relationship
            cur.execute(
                "INSERT INTO barcodes.campaigns_projects "
                "(campaign_id, project_id) "
                "VALUES (%s, 1)",
                (self.test_campaign_id, )
            )
            t.commit()

        # need to create an extra, fake campaign ID
        self.fake_campaign_id = None
        while self.fake_campaign_id is None:
            tmp_fake_campaign_id = uuid.uuid4()
            if tmp_fake_campaign_id != self.test_campaign_id:
                self.fake_campaign_id = str(tmp_fake_campaign_id)

    def tearDown(self):
        with Transaction() as t:
            cur = t.cursor()
            cur.execute(
                "DELETE FROM barcodes.campaigns_projects "
                "WHERE campaign_id = %s",
                (self.test_campaign_id,)
            )
            cur.execute(
                "DELETE FROM barcodes.campaigns "
                "WHERE campaign_id = %s",
                (self.test_campaign_id,)
            )
            t.commit()

    def test_create_interested_user_valid(self):
        dummy_user = {
            "campaign_id": self.test_campaign_id,
            "first_name": "Test",
            "last_name": "McTesterson",
            "email": "test@testing.com"
        }

        interested_user = InterestedUser.from_dict(dummy_user)

        with Transaction() as t:
            interested_user_repo = InterestedUserRepo(t)
            obs = interested_user_repo.insert_interested_user(interested_user)
            self.assertTrue(obs is not None)
            t.rollback()

    def test_create_interested_user_invalid(self):
        # test with a required field missing
        dummy_user = {
            "campaign_id": self.test_campaign_id,
            "first_name": "Test",
            "last_name": "McTesterson"
        }
        with self.assertRaises(KeyError):
            interested_user = InterestedUser.from_dict(dummy_user)

        # test with invalid campaign ID
        dummy_user = {
            "campaign_id": self.fake_campaign_id,
            "first_name": "Test",
            "last_name": "McTesterson",
            "email": "test@testing.com"
        }
        interested_user = InterestedUser.from_dict(dummy_user)
        with Transaction() as t:
            interested_user_repo = InterestedUserRepo(t)
            with self.assertRaises(ForeignKeyViolation):
                interested_user_repo.insert_interested_user(interested_user)

    def test_verify_address_already_verified(self):
        dummy_user = {
            "campaign_id": self.test_campaign_id,
            "first_name": "Test",
            "last_name": "McTesterson",
            "email": "test@testing.com",
            "address_checked": True
        }
        interested_user = InterestedUser.from_dict(dummy_user)
        with Transaction() as t:
            interested_user_repo = InterestedUserRepo(t)
            user_id = \
                interested_user_repo.insert_interested_user(interested_user)
            obs = interested_user_repo.verify_address(user_id)
            self.assertTrue(obs is None)
            t.rollback()


if __name__ == '__main__':
    unittest.main()
