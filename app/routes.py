"""Provides all routes for the Social Insecurity application.

This file contains the routes for the application. It is imported by the app package.
It also contains the SQL queries used for communicating with the database.
"""

from pathlib import Path

from flask import flash, redirect, render_template, send_from_directory, url_for

from app import app, sqlite, bcrypt, login_manager, UserMixin, login_user, current_user, logout_user
from app.forms import CommentsForm, FriendsForm, IndexForm, PostForm, ProfileForm
from html import escape
import re


def htmlify(content):
    if isinstance(content, bytes):
        return escape(content.decode('utf-8'))
    elif isinstance(content, str):
        return escape(content)
    return content

def hash_password(content):
    #salt = "this is kind of secret" 
    #yikes - each user gets an unique salt (which is (stored together with the password) using the bcrypt package)

    pw_hash = bcrypt.generate_password_hash(content)
    return pw_hash

def check_logged_in_user(user):

    if user is None:
        # User was not found in the sql query
        errMsg = {
            "type": "userDoesNotExist",
            "flash": "User not found"
        }
        return errMsg

    if not current_user.is_authenticated:
        # User is not logged in
        errMsg = {
            "type": "userIsNotLoggedIn",
            "flash": "Oh naugthy, naugthy, you have to log in"
        }
        return errMsg
    
    if int(current_user.id) != int(user["id"]):
        # User is not accessing their own logged in user page (directory traversal)
        errMsg = {
            "type": "notLoggedIntToThisUser",
            "flash": "Dont mess with other users!"
        }
        return errMsg
    
    return None # No errors found

class User(UserMixin):
    def __init__(self, user_id):
        self.id = user_id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

@app.route("/", methods=["GET", "POST"])
@app.route("/index", methods=["GET", "POST"])
def index():
    """Provides the index page for the application.

    It reads the composite IndexForm and based on which form was submitted,
    it either logs the user in or registers a new user.

    If no form was submitted, it simply renders the index page.
    """
    index_form = IndexForm()
    login_form = index_form.login
    register_form = index_form.register

    # For any redirects to index, by default the user should be logged out, could probably be done in a more clean way
    logout_user()

    if login_form.is_submitted() and login_form.submit.data:

        get_pw_hash = f"""
            SELECT password
            FROM Users
            WHERE username = '{htmlify(login_form.username.data)}';
            """ #added htmlify to avoid SQL injection
        pw_hash = sqlite.query(get_pw_hash, one=True)

        if pw_hash is None:
            flash("Sorry, this user does not exist!", category="warning")
        elif not bcrypt.check_password_hash(pw_hash["password"],login_form.password.data.encode('utf-8')):
            flash("Sorry, wrong password!", category="warning")
        else:
            get_user_id = f"""
            SELECT id
            FROM Users
            WHERE username = '{htmlify(login_form.username.data)}';
            """ 

            user_id = sqlite.query(get_user_id, one=True)
            user_id = int(user_id["id"])
            user = User(user_id)
            login_user(user)

            return redirect(url_for("stream", username=login_form.username.data))

    elif register_form.is_submitted() and register_form.submit.data and register_form.validate(register_form):
        
        # Password encryption
        pw_hash = hash_password(register_form.password.data)

        check_user = f"""
            SELECT username
            FROM Users
            WHERE username = '{htmlify(register_form.username.data)}';
        """
        if sqlite.query(check_user):
            flash("Username is taken!", category="warning")
        else:
            insert_user = f"""
                INSERT INTO Users (username, first_name, last_name, password)
                VALUES ('{htmlify(register_form.username.data)}','{htmlify(register_form.first_name.data)}',
                '{htmlify(register_form.last_name.data)}', '{htmlify(pw_hash)}');
                """
            #print(insert_user)
            sqlite.query(insert_user)
            flash("User successfully created!", category="success")
        return redirect(url_for("index"))

    return render_template("index.html.j2", title="Welcome", form=index_form)

@app.route("/stream/<string:username>", methods=["GET", "POST"])
def stream(username: str):
    """Provides the stream page for the application.

    If a form was submitted, it reads the form data and inserts a new post into the database.

    Otherwise, it reads the username from the URL and displays all posts from the user and their friends.
    """
    post_form = PostForm()
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{htmlify(username)}';
        """ #added htmlify to avoid SQL injection
    user = sqlite.query(get_user, one=True)

    # Check if the user is logged in, otherwise redirect to /index
    errMsg = check_logged_in_user(user)
    if errMsg is not None:
        flash(errMsg["flash"], category="warning")
        return redirect(url_for("index"))

    if post_form.is_submitted() and post_form.validate(): #? Added validation
        post_form.image.data.filename = re.sub(r"[\'\"/\.]", "", post_form.image.data.filename)
        #post_form.image.data.filename=post_form.image.data.filename.replace("'","").replace('"',"").replace("..","").replace("/","")
        if post_form.image.data:
            path = Path(app.instance_path) / app.config["UPLOADS_FOLDER_PATH"] / post_form.image.data.filename
            post_form.image.data.save(path)

        insert_post = f"""
            INSERT INTO Posts (u_id, content, image, creation_time)
            
            VALUES ({user["id"]}, '{htmlify(post_form.content.data)}', '{post_form.image.data.filename}', CURRENT_TIMESTAMP);
            """ #added htmlify to avoid SQL injection
        sqlite.query(insert_post)
        return redirect(url_for("stream", username=username))

    get_posts = f"""
        SELECT p.*, u.*, (SELECT COUNT(*) FROM Comments WHERE p_id = p.id) AS cc
        FROM Posts AS p JOIN Users AS u ON u.id = p.u_id
        WHERE p.u_id IN (SELECT u_id FROM Friends WHERE f_id = {user["id"]}) OR p.u_id IN (SELECT f_id FROM Friends WHERE u_id = {user["id"]}) OR p.u_id = {user["id"]}
        ORDER BY p.creation_time DESC;
        """
    posts = sqlite.query(get_posts)
    return render_template("stream.html.j2", title="Stream", username=username, form=post_form, posts=posts)


@app.route("/comments/<string:username>/<int:post_id>", methods=["GET", "POST"])
def comments(username: str, post_id: int):
    """Provides the comments page for the application.

    If a form was submitted, it reads the form data and inserts a new comment into the database.

    Otherwise, it reads the username and post id from the URL and displays all comments for the post.
    """
    comments_form = CommentsForm()
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{htmlify(username)}';
        """ #added htmlify to avoid SQL injection
    user = sqlite.query(get_user, one=True)

    # Check if the user is logged in, otherwise redirect to /index
    errMsg = check_logged_in_user(user)
    if errMsg is not None:
        flash(errMsg["flash"], category="warning")
        return redirect(url_for("index"))

    if comments_form.is_submitted():
        insert_comment = f"""
            INSERT INTO Comments (p_id, u_id, comment, creation_time)
            VALUES ({post_id}, {user["id"]}, '{comments_form.comment.data}', CURRENT_TIMESTAMP);
            """
        sqlite.query(insert_comment)

    get_post = f"""
        SELECT *
        FROM Posts AS p JOIN Users AS u ON p.u_id = u.id
        WHERE p.id = {htmlify(post_id)};
        """ #added htmlify to avoid SQL injection
    get_comments = f"""
        SELECT DISTINCT *
        FROM Comments AS c JOIN Users AS u ON c.u_id = u.id
        WHERE c.p_id={htmlify(post_id)}
        ORDER BY c.creation_time DESC;
        """ #added htmlify to avoid SQL injection
    post = sqlite.query(get_post, one=True)
    comments = sqlite.query(get_comments)
    return render_template(
        "comments.html.j2", title="Comments", username=username, form=comments_form, post=post, comments=comments
    )


@app.route("/friends/<string:username>", methods=["GET", "POST"])
def friends(username: str):
    """Provides the friends page for the application.

    If a form was submitted, it reads the form data and inserts a new friend into the database.

    Otherwise, it reads the username from the URL and displays all friends of the user.
    """
    friends_form = FriendsForm()
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{htmlify(username)}';
        """ #added htmlify to avoid SQL injection
    user = sqlite.query(get_user, one=True)

    # Check if the user is logged in, otherwise redirect to /index
    errMsg = check_logged_in_user(user)
    if errMsg is not None:
        flash(errMsg["flash"], category="warning")
        return redirect(url_for("index"))

    if friends_form.is_submitted():
        get_friend = f"""
            SELECT *
            FROM Users
            WHERE username = '{htmlify(friends_form.username.data)}';
            """ #added htmlify to avoid SQL injection
        friend = sqlite.query(get_friend, one=True)
        get_friends = f"""
            SELECT f_id
            FROM Friends
            WHERE u_id = {user["id"]};
            """
        friends = sqlite.query(get_friends)

        if friend is None:
            flash("User does not exist!", category="warning")
        elif friend["id"] == user["id"]:
            flash("You cannot be friends with yourself!", category="warning")
        elif friend["id"] in [friend["f_id"] for friend in friends]:
            flash("You are already friends with this user!", category="warning")
        else:
            insert_friend = f"""
                INSERT INTO Friends (u_id, f_id)
                VALUES ({user["id"]}, {friend["id"]});
                """
            sqlite.query(insert_friend)
            flash("Friend successfully added!", category="success")

    get_friends = f"""
        SELECT *
        FROM Friends AS f JOIN Users as u ON f.f_id = u.id
        WHERE f.u_id = {user["id"]} AND f.f_id != {user["id"]};
        """
    friends = sqlite.query(get_friends)
    return render_template("friends.html.j2", title="Friends", username=username, friends=friends, form=friends_form)


@app.route("/profile/<string:username>", methods=["GET", "POST"])
def profile(username: str):
    """Provides the profile page for the application.

    If a form was submitted, it reads the form data and updates the user's profile in the database.

    Otherwise, it reads the username from the URL and displays the user's profile.
    """
    profile_form = ProfileForm()
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{htmlify(username)}';
        """ #added htmlify to avoid SQL injection
    user = sqlite.query(get_user, one=True)

    # Check if the user is logged in, otherwise redirect to /index
    errMsg = check_logged_in_user(user)
    if errMsg is not None:
        e = errMsg["type"]
        if e == "userDoesNotExist" or e == "userIsNotLoggedIn":
            flash(errMsg["flash"], category="warning")
            return redirect(url_for("index"))        

    if profile_form.is_submitted():

        # Only logged in users with this exact user can edit the user profile
        if errMsg is not None:
            if errMsg["type"] == "notLoggedIntToThisUser":
                flash(errMsg["flash"], category="warning")
        
        else:
            update_profile = f"""
                UPDATE Users
                SET education='{htmlify(profile_form.education.data)}', employment='{htmlify(profile_form.employment.data)}',
                    music='{htmlify(profile_form.music.data)}', movie='{htmlify(profile_form.movie.data)}',
                    nationality='{htmlify(profile_form.nationality.data)}', birthday='{htmlify(profile_form.birthday.data)}'
                WHERE username='{htmlify(username)}';
                """ #added htmlify to avoid SQL injection
            sqlite.query(update_profile)
        return redirect(url_for("profile", username=username))

    return render_template("profile.html.j2", title="Profile", username=username, user=user, form=profile_form)


@app.route("/uploads/<string:filename>")
def uploads(filename):
    """Provides an endpoint for serving uploaded files."""
    return send_from_directory(Path(app.instance_path) / app.config["UPLOADS_FOLDER_PATH"], filename)
