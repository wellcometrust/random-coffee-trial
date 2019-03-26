import hashlib
import logging

from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, jsonify, request, render_template, session
from werkzeug.exceptions import Forbidden, Unauthorized
from app import db
from models import User, Department


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


auth_blueprint = Blueprint(
    'auth',
    __name__,
    template_folder='./templates'
)


def _get_hashed_password(*args):
    password = ''.join(args)
    return hashlib.sha256(password.encode()).hexdigest()


def _is_user_logged():
    """Check in the session for some user chredentials.

    Returns:
      * bool: True if a user is in the session, else False.
    """
    auth_token = session.get('auth_token')
    user = session.get('auth_user')
    if auth_token and user:
        db_user = User.query.filter_by(email=user).first()
        if db_user.expiracy_time > datetime.now():
            return db_user
    return False


def is_logged(func):
    """Decorator checking if the user is logged in.

    Args:
      * func: The function to perform if the user is logged in.

    Returns:
      * wrapper: The wrapped function

    Raises:
      * http.Unauthorized: 401 error if the user isn't logged in.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if _is_user_logged():
            return func(*args, **kwargs)
        else:
            raise Unauthorized()

    return wrapper


def is_admin(func):
    """Decorator checking if the user is an admin.

    Args:
      * func: The function to perform if the user is logged in.

    Returns:
      * wrapper: The wrapped function

    Raises:
      * http.Unauthorized: 401 error if the user isn't logged in.
      * http.Forbidden: 403 error if the user is logged in but not an admin.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = _is_user_logged()
        if user:
            if user.is_admin:
                return func(*args, **kwargs)
            else:
                # User is logged but is not admin
                raise Forbidden()
        else:
            # User is not logged
            raise Unauthorized()

    return wrapper


@auth_blueprint.route('/login', methods=['GET', 'POST'])
def get_login():
    if request.method == 'POST':
        if request.get_json():
            # Request is from api
            post_data = request.get_json()
        else:
            # Request is from form
            post_data = request.form

        if post_data.get('user_email') and post_data.get('user_password'):
            user = User.query.filter_by(
                email=post_data['user_email'],
                password=_get_hashed_password(post_data['user_password']),
                active=True,
            ).first()
            if user and user.password is not None:
                auth_token = _get_hashed_password(
                    str(datetime.now()),
                    post_data.get('user_password'),
                )
                user.auth_token = auth_token
                user.expiracy_time = datetime.now() + timedelta(days=1)
                session['auth_token'] = auth_token
                session['auth_user'] = user.email

                db.session.add(user)
                db.session.commit()
                return jsonify({
                    'status': 'success',
                    'message': 'Login complete',
                    'auth_token': auth_token,
                    'expiracy_time': user.expiracy_time,
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Unsuccessful login - Wrong id or password'
                })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Unsuccessful login'
            })
    else:
        return render_template('auth/login.html')


@auth_blueprint.route('/logout', methods=['GET'])
def logout():
    if session['auth_user']:
        user = User.query.filter_by(email=session['auth_user']).first()
        user.expiracy_time = datetime.now() - timedelta(days=2)

        db.session.add(user)
        db.session.commit()

    session['auth_user'] = None
    session['auth_token'] = None
    return jsonify({
        'status': 'success',
        'message': 'Successfully logged out.'
    })


@auth_blueprint.route('/signin', methods=['GET', 'POST'])
def create_account():
    if request.method == 'POST':
        if request.get_json():
            post_data = request.get_json()
        else:
            post_data = request.form

        fields = [
            'user_email',
            'user_password',
            'user_firstname',
            'user_lastname',
            'user_department',
        ]

        logger.info(list(map(lambda x: x in fields, post_data.keys())))
        if all(list(map(lambda x: x in fields, post_data.keys()))):
            department = Department.query.filter_by(
                name=post_data['user_department']
            ).first()
            user = User.query.filter_by(email=post_data['user_email']).first()
            if not user:
                user = User(
                    firstname=post_data['user_firstname'],
                    lastname=post_data['user_lastname'],
                    email=post_data['user_email'],
                    department_id=department.id,
                    active=True,
                )
                user.password = _get_hashed_password(
                    post_data['user_password']
                )
            else:
                # If the user has a password, it means the account has already
                # been created. If it hasn't, it only has been imported.
                if user.password:
                    return jsonify({
                        'status': 'error',
                        'message': 'A user with this email already exists'
                    })
                user.firstname = post_data['user_firstname']
                user.lastname = post_data['user_lastname']
                user.password = post_data['user_password']
                user.active = True

            db.session.add(user)
            db.session.commit()
            return jsonify({
                'status': 'success',
                'user': user.to_dict(),
                'message': 'User successfully created!'
            })
    else:
        departments = Department.query.all()
        return render_template('auth/signin.html', departments=departments)
