import datetime
import psycopg2

from microsetta_private_api.repo.base_repo import BaseRepo
from microsetta_private_api.model.account import Account, AuthorizationMatch
from microsetta_private_api.model.address import Address
from microsetta_private_api.exceptions import RepoException


class AccountRepo(BaseRepo):
    def __init__(self, transaction):
        super().__init__(transaction)

    read_cols = "id, email, " \
                "account_type, auth_issuer, auth_sub, " \
                "first_name, last_name, " \
                "street, street2, city, state, post_code, country_code, " \
                "created_with_kit_id, preferred_language, " \
                "consent_privacy_terms, creation_time, update_time, " \
                "latitude, longitude, "\
                "cannot_geocode"

    write_cols = "id, email, " \
                 "account_type, auth_issuer, auth_sub, " \
                 "first_name, last_name, " \
                 "street, street2, city, state, post_code, country_code, " \
                 "preferred_language, latitude, longitude, cannot_geocode, " \
                 "consent_privacy_terms"

    @staticmethod
    def _row_to_addr(r):
        return Address(r["street"], r["city"], r["state"], r["post_code"],
                       r["country_code"], r["street2"])

    @staticmethod
    def _addr_to_row(addr):
        return (addr.street,
                addr.street2,
                addr.city,
                addr.state,
                addr.post_code,
                addr.country_code)

    @staticmethod
    def _row_to_account(r):
        return Account(
            r['id'], r['email'],
            r['account_type'], r['auth_issuer'], r['auth_sub'],
            r['first_name'], r['last_name'],
            AccountRepo._row_to_addr(r),
            r['latitude'], r['longitude'], r['cannot_geocode'],
            r['preferred_language'],
            r['consent_privacy_terms'],
            r['created_with_kit_id'],
            r['creation_time'], r['update_time'])

    @staticmethod
    def _account_to_row(a):
        return (a.id, a.email,
                a.account_type, a.auth_issuer, a.auth_sub,
                a.first_name, a.last_name) + \
                AccountRepo._addr_to_row(a.address) + \
                (a.language, a.latitude, a.longitude,
                 a.cannot_geocode, a.consent_privacy_terms)

    def claim_legacy_account(self, email, auth_iss, auth_sub):
        # Returns now-claimed legacy account if an unclaimed legacy account
        # that matched the input email was found; otherwise returns None.
        # (Note that None is returned in the case where there is a NON-legacy
        # account with the input email--find such accounts with
        # find_linked_account instead.) Throws a RepoException
        # if logic indicates inconsistent auth info.

        found_account = self._find_account_by_email(email)
        # if no account is found by email, just return none.
        if found_account is None:
            return None

        auth = found_account.account_matches_auth(email, auth_iss, auth_sub)

        if auth == AuthorizationMatch.FULL_MATCH:
            return None
        elif auth == AuthorizationMatch.LEGACY_MATCH:
            # this is a legacy account from before we used an external
            # authorization provider. claim it for this authorized user.
            found_account.auth_issuer = auth_iss
            found_account.auth_sub = auth_sub
            self.update_account(found_account)
            return found_account
        elif auth == AuthorizationMatch.NO_MATCH:
            # any other situation is an error and shouldn't happen,
            # e.g. one of auth_iss or auth_sub is null in db but the other
            # isn't, or one or more of non-null auth_iss and auth_sub values
            # in db do not match the analogous input auth_iss and auth_sub
            # values for the provided email ... may be more edge cases as well
            raise RepoException("Inconsistent data found for provided email.")
        else:
            raise ValueError("Unknown authorization match value")

    def _find_account_by_email(self, email):
        # select from account table anything that has this email.

        with self._transaction.dict_cursor() as cur:
            cur.execute("SELECT " + AccountRepo.read_cols + " FROM "
                        "account "
                        "WHERE "
                        "account.email = %s", (email,))

            # Do not need to check for multiple results because index on
            # field in db table guarantees uniqueness.
            r = cur.fetchone()

            # if no account with the email was found, return None
            if r is None:
                return None
            else:
                return AccountRepo._row_to_account(r)

    def find_linked_account(self, auth_iss, auth_sub):
        with self._transaction.dict_cursor() as cur:
            cur.execute("SELECT " + AccountRepo.read_cols + " FROM "
                        "account "
                        "WHERE "
                        "account.auth_issuer = %s AND "
                        "account.auth_sub = %s", (auth_iss, auth_sub))
            r = cur.fetchone()
            if r is None:
                return None
            else:
                return AccountRepo._row_to_account(r)

    def get_account(self, account_id):
        with self._transaction.dict_cursor() as cur:
            cur.execute("SELECT " + AccountRepo.read_cols + " FROM "
                        "ag.account "
                        "WHERE "
                        "account.id = %s", (account_id,))
            r = cur.fetchone()
            if r is None:
                return None
            else:
                return AccountRepo._row_to_account(r)

    def update_account(self, account):
        with self._transaction.cursor() as cur:
            row = AccountRepo._account_to_row(account)

            # remove consent_privacy_terms from the row since we don't
            # update it
            consent_pos = len(row) - 1
            row = row[:consent_pos]

            # Shift id to end since it appears in the WHERE clause
            row_id = row[0:1]
            row_email_to_cc = row[1:]
            final_row = row_email_to_cc + row_id
            try:
                cur.execute("UPDATE account "
                            "SET "
                            "email = %s, "
                            "account_type = %s, "
                            "auth_issuer = %s, "
                            "auth_sub = %s, "
                            "first_name = %s, "
                            "last_name = %s, "
                            "street = %s, "
                            "street2 = %s, "
                            "city = %s, "
                            "state = %s, "
                            "post_code = %s, "
                            "country_code = %s, "
                            "preferred_language = %s, "
                            "latitude = %s, "
                            "longitude = %s, "
                            "cannot_geocode = %s "
                            "WHERE "
                            "account.id = %s",
                            final_row
                            )
                return cur.rowcount == 1
            except psycopg2.errors.UniqueViolation as e:
                if e.diag.constraint_name == 'idx_account_email':
                    # TODO: Ugh. Localization of error messages is needed.
                    raise RepoException("Email %s is not available"
                                        % account.email) from e
                if e.diag.constraint_name == 'idx_account_issuer_sub':
                    # Ugh.  This is really difficult to explain to an end user.
                    raise RepoException("Cannot claim more than one account")
                # Unknown exception, re raise it.
                raise e

    def create_account(self, account):
        try:
            with self._transaction.cursor() as cur:
                cur.execute("INSERT INTO ag.account (" +
                            AccountRepo.write_cols +
                            ") "
                            "VALUES("
                            "%s, %s, "
                            "%s, %s, %s, "
                            "%s, %s, "
                            "%s, %s, %s, %s, %s, "
                            "%s, %s, %s, %s, %s)",
                            AccountRepo._account_to_row(account))
                return cur.rowcount == 1
        except psycopg2.errors.UniqueViolation as e:
            if e.diag.constraint_name == 'idx_account_email':
                # TODO: Ugh. Localization of error messages is needed someday.
                raise RepoException("Email %s is not available"
                                    % account.email) from e
            if e.diag.constraint_name == 'idx_account_issuer_sub':
                # Ugh.  This is really difficult to explain to an end user.
                raise RepoException("Cannot create two accounts on the same "
                                    "email")

            # Unknown exception, re raise it.
            raise e

    def delete_account(self, account_id):
        with self._transaction.cursor() as cur:
            cur.execute("DELETE FROM account WHERE account.id = %s",
                        (account_id,))
            return cur.rowcount == 1

    def delete_account_by_email(self, email):
        with self._transaction.cursor() as cur:
            cur.execute("DELETE FROM account WHERE account.email = %s",
                        (email,))
            return cur.rowcount == 1

    def get_account_ids_by_email(self, email):
        email = "%"+email+"%"
        with self._transaction.cursor() as cur:
            # ILIKE is case insensitive LIKE
            cur.execute("SELECT id FROM account WHERE email ILIKE %s "
                        "ORDER BY email",
                        (email,))
            return [x[0] for x in cur.fetchall()]

    def scrub(self, account_id):
        """Remove any identifying information from the account

        Parameters
        ----------
        account_id : uuid
            The account to scrub details from

        Returns
        -------
        bool
            True if the account was successfully scrubbed
        """
        account = self.get_account(account_id)

        if account is None:
            raise RepoException(f"account ({account_id}) does not exist")

        # email must be unique. let's construct using the present time
        # so we know when the account was scrubbed indefinitely. using time
        # creates a possible race condition with the email, so we'll include
        # the account ID as well to ensure uniqueness. we quote the email
        # address so that it remains technically valid; quoting of ":" is
        # necessary, see https://stackoverflow.com/a/2049510
        date = datetime.datetime.now().isoformat()
        email = f'"{date}_{account.id}_scrubbed"@microsetta.ucsd.edu'

        account.email = email
        account.account_type = 'deleted'
        account.auth_issuer = None
        account.auth_sub = None
        account.first_name = 'scrubbed'
        account.last_name = 'scrubbed'
        account.address.street = 'scrubbed'
        account.address.street2 = 'scrubbed'
        account.address.city = 'scrubbed'
        account.address.state = 'NA'
        account.address.post_code = 'scrubbed'
        account.latitude = None
        account.longitude = None
        account.cannot_geocode = False

        return self.update_account(account) == 1
