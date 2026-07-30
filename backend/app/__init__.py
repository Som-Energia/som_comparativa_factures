from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge

from .routes import api


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
    CORS(app)
    app.register_blueprint(api, url_prefix="/api")

    @app.errorhandler(RequestEntityTooLarge)
    def upload_too_large(_error):
        return jsonify({"errors": {"pdf": "El PDF no pot superar els 10 MB."}}), 413

    return app
