import datetime
from flask.json import JSONEncoder
from dateutil.parser import isoparse


class PerksType:
    FFQ = 'FFQ'
    FFQ_KIT = 'FFQ_KIT'
    FFQ_ONE_YEAR = 'FFQ_ONE_YEAR'


class JsonifyDefaultEncoder(JSONEncoder):
    def default(self, o):
        return json_converter(o)


def fromisotime(s):
    return isoparse(s)


def json_converter(o):
    if isinstance(o, datetime.datetime) or isinstance(o, datetime.date):
        return o.isoformat()
    return o.__dict__
