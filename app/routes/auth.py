from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user

from ..extensions import db, oauth
from ..models import AuthAccount, User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        nickname = request.form["nickname"].strip()
        password = request.form["password"]

        if AuthAccount.query.filter_by(provider="LOCAL", login_id=email).first():
            flash("이미 가입된 이메일입니다.")
            return redirect(url_for("auth.signup"))
        if User.query.filter_by(nickname=nickname).first():
            flash("이미 사용 중인 닉네임입니다.")
            return redirect(url_for("auth.signup"))

        user = User(email=email, nickname=nickname)
        db.session.add(user)
        db.session.flush()  # user.id 확보 (auth_accounts에서 FK로 필요)

        account = AuthAccount(user_id=user.id, provider="LOCAL", login_id=email)
        account.set_password(password)
        db.session.add(account)
        db.session.commit()

        login_user(user)
        return redirect(url_for("pages.index"))

    return render_template("auth/signup.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        account = AuthAccount.query.filter_by(provider="LOCAL", login_id=email).first()
        if account is None or not account.check_password(password):
            flash("이메일 또는 비밀번호가 올바르지 않습니다.")
            return redirect(url_for("auth.login"))

        account.last_login_at = datetime.utcnow()
        db.session.commit()

        login_user(account.user)
        return redirect(url_for("pages.index"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("pages.index"))


@auth_bp.route("/auth/google/login")
def google_login():
    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/google/callback")
def google_callback():
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email")
    google_sub = userinfo.get("sub")

    if not email or not google_sub:
        flash("구글 계정 정보를 가져오지 못했습니다.")
        return redirect(url_for("auth.login"))

    account = AuthAccount.query.filter_by(provider="GOOGLE", google_sub=google_sub).first()
    if account is not None:
        account.last_login_at = datetime.utcnow()
        db.session.commit()
        login_user(account.user)
        return redirect(url_for("pages.index"))

    user = User.query.filter_by(email=email).first()
    if user is None:
        nickname = userinfo.get("name") or email.split("@")[0]
        if User.query.filter_by(nickname=nickname).first():
            nickname = f"{nickname}-{google_sub[-6:]}"
        user = User(email=email, nickname=nickname)
        db.session.add(user)
        db.session.flush()

    account = AuthAccount(
        user_id=user.id,
        provider="GOOGLE",
        google_sub=google_sub,
        last_login_at=datetime.utcnow(),
    )
    db.session.add(account)
    db.session.commit()

    login_user(user)
    return redirect(url_for("pages.index"))
