from authlib.integrations.flask_oauth2 import AuthorizationServer
from authlib.integrations.sqla_oauth2 import (
    create_query_client_func,
    create_save_token_func
)
from authlib.jose import JsonWebKey, KeySet
from flask import Flask, request, render_template

app = Flask(__name__)

from models import db, AuthorizationCode, Client, Token, User
from auth import AuthorizationCodeGrant, OpenIDCode


# Load configuration--default, then custom. Path to latter set in Dockerfile.
app.config.from_object('default_settings')
app.config.from_envvar('PATH_TO_APP_CONFIG')

# Configure app to work with SQLAlchemy
db.init_app(app)
# Create tables.
# SQLAlchemy object not bound to app, so pass in app as arg.
# Alternatively could push an app context.
db.create_all(app=app)


query_client = create_query_client_func(db.session, Client)
save_token = create_save_token_func(db.session, Token)

server = AuthorizationServer(
    app, query_client=query_client, save_token=save_token
)

# register AuthorizationCodeGrant to grant endpoint
server.register_grant(AuthorizationCodeGrant, [OpenIDCode(require_nonce=False)])


def get_or_create_shib_user():
    if request.remote_user:
        user = User.query.filter(User.shib_id == request.remote_user).one_or_none()
        if not user:
            print("User not found in db; creating...")
            new_user = User(shib_id=request.remote_user)
            db.session.add(new_user)
            db.session.commit()
            print("User created.")
            user = new_user
        return user
    return "No value for request.remote_user--is this being called outside a request context?"


@app.route('/oauth/authorize', methods=['GET', 'POST'])
def authorize():
    current_user = get_or_create_shib_user()

    if request.method == 'GET':
        grant = server.validate_consent_request(end_user=current_user)
        return render_template(
            'authorize.html',
            grant=grant,
            user=current_user,
        )
    confirmed = request.form['confirm']
    if confirmed:
        # granted by resource owner
        return server.create_authorization_response(grant_user=current_user)
    # denied by resource owner
    return server.create_authorization_response(grant_user=None)


@app.route('/oauth/token', methods=['POST'])
def issue_token():
    """
    The client should make the request with a Basic auth header and
    Content-Type: application/x-www-form-urlencoded
    """
    return server.create_token_response()


@app.route('/.well-known/oauth-authorization-server')
def well_known():
    return server.metadata


@app.route('/jwks.json')
def jwks():
    with open(app.config["PUBLIC_KEY_PATH"]) as f:
        public_key_data = f.read()
    public_key = JsonWebKey.import_key(public_key_data, {"kty": "RSA"})
    keyset = KeySet([public_key])
    return keyset.as_json()
