from quart import jsonify
from werkzeug.exceptions import HTTPException


class APIException(HTTPException):
    def __init__(self, status_code, data) -> None:
        response = jsonify(data)
        response.status_code = status_code
        super().__init__(response=response)
