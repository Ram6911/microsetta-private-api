import pytest
import werkzeug
import json
import copy
import collections
from urllib.parse import urlencode
from unittest import TestCase
import microsetta_private_api.server
from microsetta_private_api.repo.transaction import Transaction
from microsetta_private_api.repo.account_repo import AccountRepo
from microsetta_private_api.model.account import Account


# region helper methods
QUERY_KEY = "query"
CONTENT_KEY = "content"

TEST_EMAIL = "test_email@example.com"
TEST_EMAIL_2 = "second_test_email@example.com"
KIT_NAME_KEY = "kit_name"
# these kits exists in the test db (NOT created by unit test code)
EXISTING_KIT_NAME = "jb_qhxqe"
EXISTING_KIT_NAME_2 = "fa_lrfiq"
# this kit does not exist in the test db
MISSING_KIT_NAME = "jb_qhxTe"
MISSING_ACCT_ID = "a6cbd48e-f8da-4c0e-bdd6-3ffbbb5958ba"
DUMMY_ACCT_INFO = {
    "address": {
        "city": "Springfield",
        "country_code": "US",
        "post_code": "12345",
        "state": "CA",
        "street": "123 Main St. E. Apt. 2"
    },
    "email": TEST_EMAIL,
    "first_name": "Jane",
    "last_name": "Doe",
    KIT_NAME_KEY: EXISTING_KIT_NAME
}
DUMMY_ACCT_INFO_2 = {
    "address": {
        "city": "Oberlin",
        "country_code": "US",
        "post_code": "44074",
        "state": "OH",
        "street": "489 College St."
    },
    "email": TEST_EMAIL_2,
    "first_name": "Obie",
    "last_name": "Dobie",
    KIT_NAME_KEY: EXISTING_KIT_NAME_2
}

ACCT_ID_KEY = "account_id"
ACCT_TYPE_KEY = "account_type"
ACCT_TYPE_VAL = "standard"
CREATION_TIME_KEY = "creation_time"
UPDATE_TIME_KEY = "update_time"


def dictionary_mangler(a_dict, delete_fields=True, parent_dicts=None):
    """Generator to delete fields or add bogus fields in nested dictionary.

    Create a generator to travel recursively through the provided dictionary
    (which may contain child dictionaries).  If delete_fields, then for every
    leaf field, yield a copy of the whole dictionary with just that field
    deleted.  If not delete_fields, then for every leaf dictionary, yield a
    copy of the whole dictionary with one unexpected, bogus field added."""
    if parent_dicts is None:
        parent_dicts = collections.OrderedDict()
        parent_dicts["top"] = copy.deepcopy(a_dict)
    curr_dicts = {}

    for curr_key, curr_val in a_dict.items():
        curr_dicts = copy.deepcopy(parent_dicts)
        if isinstance(curr_val, dict):
            curr_dicts[curr_key] = curr_val
            yield from dictionary_mangler(curr_val, delete_fields,
                                          curr_dicts)
        else:
            if delete_fields:
                yield mangle_dictionary(a_dict, curr_dicts, curr_key)

    if not delete_fields:
        if curr_dicts is None:
            curr_dicts = copy.deepcopy(parent_dicts)
        yield mangle_dictionary(a_dict, curr_dicts)


def mangle_dictionary(a_dict, curr_dicts, key_to_delete=None):
    """Return copy of nested dictionary with a field popped or added.

     The popped or added field may be at any level of nesting within the
     original dictionary.  `curr_dicts` is an OrderedDict containing each
     nested dictionary in the original dictionary we are looping through
     (not necessarily the same as a_dict).  The first entry has the key "top"
     and holds the entire original dictionary. The second entry has the key of
     whatever the first nested dictionary is, and the value of that whole
     nested dictionary.  If that has nested dictionaries
     within it, they will be represented in the subsequent key/values, etc."""
    curr_dict = a_dict.copy()
    if key_to_delete is not None:
        curr_dict.pop(key_to_delete)
    else:
        curr_dict["disallowed_key"] = "bogus_value"
    curr_parent_key, _ = curr_dicts.popitem(True)

    q = len(curr_dicts.keys())
    while q > 0:
        next_parent_key, next_parent_dict = curr_dicts.popitem(True)
        next_parent_dict[curr_parent_key] = copy.deepcopy(curr_dict)
        curr_dict = copy.deepcopy(next_parent_dict)
        curr_parent_key = next_parent_key
        q = q - 1

    return curr_dict


def extract_last_id_from_location_header(response):
    last_path_id = None
    try:
        loc = response.headers.get("Location")
        url = werkzeug.urls.url_parse(loc)
        last_path_id = url.path.split('/')[-1]
    finally:
        return last_path_id


def delete_dummy_accts():
    with Transaction() as t:
        AccountRepo(t).delete_account_by_email(TEST_EMAIL)
        AccountRepo(t).delete_account_by_email(TEST_EMAIL_2)
        t.commit()


def create_dummy_acct(create_dummy_1=True):
    if create_dummy_1:
        dummy_acct_id = "7a98df6a-e4db-40f4-91ec-627ac315d881"
        dict_to_copy = DUMMY_ACCT_INFO
    else:
        dummy_acct_id = "9457c58f-7464-46c9-b6e0-116273cf8f28"
        dict_to_copy = DUMMY_ACCT_INFO_2

    input_obj = copy.deepcopy(dict_to_copy)
    input_obj["id"] = dummy_acct_id
    with Transaction() as t:
        acct_repo = AccountRepo(t)
        acct_repo.create_account(Account.from_dict(input_obj))
        t.commit()

    return dummy_acct_id
# endregion help methods


@pytest.fixture(scope="class")
def client(request):
    app = microsetta_private_api.server.build_app()
    app.app.testing = True
    with app.app.test_client() as client:
        request.cls.client = client
        yield client


@pytest.mark.usefixtures("client")
class FlaskTests(TestCase):
    lang_query_dict = {
        "language_tag": "en_US"
    }

    dummy_auth = {'Authorization': 'Bearer PutMySecureOauthTokenHere'}

    default_lang_tag = lang_query_dict["language_tag"]

    def setUp(self):
        app = microsetta_private_api.server.build_app()
        self.client = app.app.test_client()
        # This isn't perfect, due to possibility of exceptions being thrown
        # is there some better pattern I can use to split up what should be
        # a 'with' call?
        self.client.__enter__()

    def tearDown(self):
        # This isn't perfect, due to possibility of exceptions being thrown
        # is there some better pattern I can use to split up what should be
        # a 'with' call?
        self.client.__exit__(None, None, None)

    def run_query_and_content_required_field_test(self, url, action,
                                                  valid_query_dict,
                                                  valid_content_dict=None):

        if valid_content_dict is None:
            valid_content_dict = {}
        dicts_to_test = {QUERY_KEY: valid_query_dict,
                         CONTENT_KEY: valid_content_dict}

        for curr_dict_type, dict_to_test in dicts_to_test.items():
            curr_query_dict = valid_query_dict
            curr_content_dict = valid_content_dict
            curr_expected_msg = None

            field_deleter = dictionary_mangler(dict_to_test,
                                               delete_fields=True)

            for curr_mangled_dict in field_deleter:
                if curr_dict_type == QUERY_KEY:
                    curr_query_dict = curr_mangled_dict
                    curr_expected_msg = "Missing query parameter "
                elif curr_dict_type == CONTENT_KEY:
                    curr_content_dict = curr_mangled_dict
                    curr_expected_msg = "is a required property"

                curr_query_str = urlencode(curr_query_dict)
                curr_content_json = json.dumps(curr_content_dict)
                curr_url = url if not curr_query_str else \
                    '{0}?{1}'.format(url, curr_query_str)
                if action == "get":
                    response = self.client.get(
                        curr_url,
                        headers=self.dummy_auth)
                elif action == "post":
                    response = self.client.post(
                        curr_url,
                        headers=self.dummy_auth,
                        content_type='application/json',
                        data=curr_content_json)
                elif action == "put":
                    response = self.client.put(
                        curr_url,
                        headers=self.dummy_auth,
                        content_type='application/json',
                        data=curr_content_json)
                else:
                    raise ValueError(format("unexpect request action: ",
                                            action))

                self.assertEqual(400, response.status_code)
                resp_obj = json.loads(response.data)
                self.assertTrue(curr_expected_msg in resp_obj['detail'])
            # next deleted field
        # next dict to test

    def validate_dummy_acct_response_body(self, response_obj,
                                          dummy_acct_dict=None):
        if dummy_acct_dict is None:
            dummy_acct_dict = DUMMY_ACCT_INFO

        # check expected additional fields/values appear in response body:
        # Note that "d.get()" returns none if key not found, doesn't throw err
        real_acct_id_from_body = response_obj.get(ACCT_ID_KEY)
        self.assertIsNotNone(real_acct_id_from_body)

        real_acct_type = response_obj.get(ACCT_TYPE_KEY)
        self.assertEqual(ACCT_TYPE_VAL, real_acct_type)

        real_creation_time = response_obj.get(CREATION_TIME_KEY)
        self.assertIsNotNone(real_creation_time)

        real_update_time = response_obj.get(UPDATE_TIME_KEY)
        self.assertIsNotNone(real_update_time)

        # check all input fields/values appear in response body EXCEPT kit_name
        # plus additional fields
        expected_dict = copy.deepcopy(dummy_acct_dict)
        try:
            expected_dict.pop(KIT_NAME_KEY)
        except KeyError:
            # is ok if input did not have a kit name, as this is
            # provided on account create but not account update
            pass
        expected_dict[ACCT_ID_KEY] = real_acct_id_from_body
        expected_dict[ACCT_TYPE_KEY] = ACCT_TYPE_VAL
        expected_dict[CREATION_TIME_KEY] = real_creation_time
        expected_dict[UPDATE_TIME_KEY] = real_update_time
        self.assertEqual(expected_dict, response_obj)

        return real_acct_id_from_body


@pytest.mark.usefixtures("client")
class AccountsTests(FlaskTests):
    def setUp(self):
        super().setUp()
        delete_dummy_accts()

    def tearDown(self):
        super().tearDown()
        delete_dummy_accts()

    # region accounts create/post tests
    def test_accounts_create_success(self):
        """Successfully create a new account"""

        # create post input json
        input_json = json.dumps(DUMMY_ACCT_INFO)

        # execute accounts post (create)
        response = self.client.post(
            '/api/accounts?language_tag=%s' % self.default_lang_tag,
            content_type='application/json',
            data=input_json
        )

        # check response code
        self.assertEqual(201, response.status_code)

        # load the response body
        response_obj = json.loads(response.data)

        # check all elements of account object in body are correct
        real_acct_id_from_body = self.validate_dummy_acct_response_body(
            response_obj)

        # check location header was provided, with new acct id
        real_acct_id_from_loc = extract_last_id_from_location_header(response)
        self.assertIsNotNone(real_acct_id_from_loc)

        # check account id provided in body matches that in location header
        self.assertTrue(real_acct_id_from_loc, real_acct_id_from_body)

    def test_accounts_create_fail_400_without_required_fields(self):
        """Return 400 validation fail if don't provide a required field """

        self.run_query_and_content_required_field_test("/api/accounts", "post",
                                                       self.lang_query_dict,
                                                       DUMMY_ACCT_INFO)

    def test_accounts_create_fail_404(self):
        """Return 404 if provided kit name is not found in db."""

        # create post input json
        input_obj = copy.deepcopy(DUMMY_ACCT_INFO)
        input_obj[KIT_NAME_KEY] = MISSING_KIT_NAME
        input_json = json.dumps(input_obj)

        # execute accounts post (create)
        response = self.client.post(
            '/api/accounts?language_tag=%s' % self.default_lang_tag,
            content_type='application/json',
            data=input_json
        )

        # check response code
        self.assertEqual(404, response.status_code)

    def test_accounts_create_fail_422(self):
        """Return 422 if provided email is in use in db."""

        # NB: I would rather do this with an email already in use in the
        # test db, but it appears the test db emails have been randomized
        # into strings that won't pass the api's email format validation :(
        create_dummy_acct(create_dummy_1=True)

        # Now try to create a new account that is different in all respects
        # from the first dummy one EXCEPT that it has the same email
        test_acct_info = copy.deepcopy(DUMMY_ACCT_INFO_2)
        test_acct_info["email"] = TEST_EMAIL

        # create post input json
        input_json = json.dumps(test_acct_info)

        # execute accounts post (create)
        response = self.client.post(
            '/api/accounts?language_tag=%s' % self.default_lang_tag,
            content_type='application/json',
            data=input_json
        )

        # check response code
        self.assertEqual(422, response.status_code)
        # endregion accounts create/post tests


@pytest.mark.usefixtures("client")
class AccountTests(FlaskTests):
    def setUp(self):
        super().setUp()
        delete_dummy_accts()

    def tearDown(self):
        super().tearDown()
        delete_dummy_accts()

    # region account view/get tests
    def test_account_view_success(self):
        """Successfully view existing account"""
        dummy_acct_id = create_dummy_acct(create_dummy_1=True)

        response = self.client.get(
            '/api/accounts/%s?language_tag=%s' %
            (dummy_acct_id, self.default_lang_tag),
            headers=self.dummy_auth)

        # check response code
        self.assertEqual(200, response.status_code)

        # load the response body
        response_obj = json.loads(response.data)

        # check all elements of account object in body are correct
        self.validate_dummy_acct_response_body(response_obj)

    def test_account_view_fail_400_without_required_fields(self):
        """Return 400 validation fail if don't provide a required field """

        dummy_acct_id = create_dummy_acct()

        input_url = "/api/accounts/{0}".format(dummy_acct_id)
        self.run_query_and_content_required_field_test(input_url, "get",
                                                       self.lang_query_dict)

    def test_account_view_fail_404(self):
        """Return 404 if provided account id is not found in db."""

        response = self.client.get(
            '/api/accounts/%s?language_tag=%s' %
            (MISSING_ACCT_ID, self.default_lang_tag),
            headers=self.dummy_auth)

        # check response code
        self.assertEqual(404, response.status_code)
    # endregion account view/get tests

    # region account update/put tests
    @staticmethod
    def make_updated_acct_dict():
        result = copy.deepcopy(DUMMY_ACCT_INFO)
        result.pop(KIT_NAME_KEY)

        result["address"] = {
            "city": "Oakland",
            "country_code": "US",
            "post_code": "99228",
            "state": "CA",
            "street": "641 Queen St. E"
        }

        return result

    def test_account_update_success(self):
        """Successfully update existing account"""
        dummy_acct_id = create_dummy_acct()

        changed_acct_dict = self.make_updated_acct_dict()

        # create post input json
        input_json = json.dumps(changed_acct_dict)

        response = self.client.put(
            '/api/accounts/%s?language_tag=%s' %
            (dummy_acct_id, self.default_lang_tag),
            headers=self.dummy_auth,
            content_type='application/json',
            data=input_json)

        # check response code
        self.assertEqual(200, response.status_code)

        # load the response body
        response_obj = json.loads(response.data)

        # check all elements of account object in body are correct
        self.validate_dummy_acct_response_body(response_obj,
                                               changed_acct_dict)

    def test_account_update_fail_400_without_required_fields(self):
        """Return 400 validation fail if don't provide a required field """

        dummy_acct_id = create_dummy_acct()
        changed_acct_dict = self.make_updated_acct_dict()

        input_url = "/api/accounts/{0}".format(dummy_acct_id)
        self.run_query_and_content_required_field_test(input_url, "put",
                                                       self.lang_query_dict,
                                                       changed_acct_dict)

    def test_account_update_fail_404(self):
        """Return 404 if provided account id is not found in db."""

        changed_acct_dict = self.make_updated_acct_dict()

        # create post input json
        input_json = json.dumps(changed_acct_dict)

        response = self.client.put(
            '/api/accounts/%s?language_tag=%s' %
            (MISSING_ACCT_ID, self.default_lang_tag),
            headers=self.dummy_auth,
            content_type='application/json',
            data=input_json)

        # check response code
        self.assertEqual(404, response.status_code)

    def test_accounts_update_fail_422(self):
        """Return 422 if provided email is in use in db."""

        # NB: I would rather do this with an email already in use in the
        # test db, but it appears the test db emails have been randomized
        # into strings that won't pass the api's email format validation :(
        create_dummy_acct(create_dummy_1=False)

        dummy_acct_id = create_dummy_acct(create_dummy_1=True)
        # Now try to update the account with info that is the same in
        # all respects from the dummy one EXCEPT that it has
        # an email that is already in use by ANOTHER account
        changed_dummy_acct = copy.deepcopy(DUMMY_ACCT_INFO)
        changed_dummy_acct["email"] = TEST_EMAIL_2

        # create post input json
        input_json = json.dumps(changed_dummy_acct)

        response = self.client.put(
            '/api/accounts/%s?language_tag=%s' %
            (dummy_acct_id, self.default_lang_tag),
            headers=self.dummy_auth,
            content_type='application/json',
            data=input_json)

        # check response code
        self.assertEqual(422, response.status_code)