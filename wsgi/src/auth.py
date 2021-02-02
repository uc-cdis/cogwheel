from authlib.oauth2.rfc6749 import grants as oauth2grants
from authlib.oidc.core import grants as oidcgrants
from authlib.oidc.core import UserInfo
from flask import request

from main import app
from models import db, AuthorizationCode, User

class AuthorizationCodeGrant(oauth2grants.AuthorizationCodeGrant):

    def save_authorization_code(self, code, request):
        # openid request MAY have "nonce" parameter
        nonce = request.data.get('nonce')
        client = request.client
        auth_code = AuthorizationCode(
            code=code,
            client_id=client.client_id,
            redirect_uri=request.redirect_uri,
            scope=request.scope,
            user_id=request.user.id,
            nonce=nonce,
        )
        db.session.add(auth_code)
        db.session.commit()
        return auth_code

    def query_authorization_code(self, code, client):
        item = AuthorizationCode.query.filter_by(
            code=code, client_id=client.client_id).first()
        if item and not item.is_expired():
            return item

    def delete_authorization_code(self, authorization_code):
        db.session.delete(authorization_code)
        db.session.commit()

    def authenticate_user(self, authorization_code):
        return User.query.get(authorization_code.user_id)


class OpenIDCode(oidcgrants.OpenIDCode):
    def exists_nonce(self, nonce, request):
        exists = AuthorizationCode.query.filter_by(
            client_id=request.client_id, nonce=nonce
        ).first()
        return bool(exists)

    def get_jwt_config(self, grant):
        """Get the JWT configuration for OpenIDCode extension. The JWT
        configuration will be used to generate ``id_token``.
        """
        # Get iss/hostname from WSGI environment, i.e. from Apache VirtualHost config,
        # to eliminate the need to manually configure the WSGI app with a hostname and
        # then manually ensure that both config values match
        iss = request.environ['SERVER_NAME']

        # Read in private signing key
        with open(app.config["PRIVATE_KEY_PATH"]) as f:
            private_key = f.read()

        return {
            'key': private_key,
            'alg': 'RS256',
            'iss': iss,
            'exp': 3600,
        }

    def generate_user_info(self, user, scope):
        # The "sub" claim should either be unique issuer-wide or
        # globally unique, and it should be a StringOrURI.
        # Technically a stringified user.id would be issuer-unique,
        # but I think it is more sensible to just use user.shib_id.
        # Will still also publish "shib_id" field.

        user_info = UserInfo(sub=user.shib_id, shib_id=user.shib_id)

        # Add this when can get the "mail" SAML Attribute!
        #if 'email' in scope:
        #    user_info['email'] = user.email

        # Gen3/Fence hack for use with Fence's "Cognito" IdP,
        # which requires an "email" field...
        user_info['email'] =  user.shib_id
        user_info['email_verified'] =  True

        return user_info
