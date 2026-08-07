from datetime import datetime, timezone

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..extensions import db, oauth
from ..models import AuthAccount, User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        nickname = request.form.get("nickname", "").strip()
        password = request.form.get("password", "")

        if not email or not nickname or not password:
            flash("이메일, 닉네임, 비밀번호를 모두 입력해 주세요.")
            return redirect(url_for("auth.signup"))
        if len(nickname) > 50:
            flash("닉네임은 50자 이하여야 합니다.")
            return redirect(url_for("auth.signup"))
        if not 8 <= len(password) <= 128:
            flash("비밀번호는 8자 이상 128자 이하여야 합니다.")
            return redirect(url_for("auth.signup"))

        if User.query.filter_by(email=email).first():
            flash("이미 가입된 이메일입니다. 기존 로그인 방법을 이용해 주세요.")
            return redirect(url_for("auth.signup"))
        if User.query.filter_by(nickname=nickname).first():
            flash("이미 사용 중인 닉네임입니다.")
            return redirect(url_for("auth.signup"))

        try:
            user = User(email=email, nickname=nickname)
            db.session.add(user)
            db.session.flush()  # user.id 확보 (auth_accounts에서 FK로 필요)

            account = AuthAccount(user_id=user.id, provider="LOCAL", login_id=email)
            account.set_password(password)
            db.session.add(account)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("이미 사용 중인 이메일 또는 닉네임입니다.")
            return redirect(url_for("auth.signup"))
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to create local account")
            flash("회원가입 정보를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
            return redirect(url_for("auth.signup"))

        login_user(user)
        return redirect(url_for("pages.index"))

    return render_template("auth/signup.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("이메일과 비밀번호를 입력해 주세요.")
            return redirect(url_for("auth.login"))

        account = AuthAccount.query.filter_by(provider="LOCAL", login_id=email).first()
        if account is None or not account.check_password(password):
            flash("이메일 또는 비밀번호가 올바르지 않습니다.")
            return redirect(url_for("auth.login"))

        account.last_login_at = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to update local login time")
            flash("로그인 정보를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
            return redirect(url_for("auth.login"))

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
    try:
        return oauth.google.authorize_redirect(redirect_uri)
    except Exception:
        current_app.logger.exception("Failed to start Google OAuth")
        flash("Google 로그인을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return redirect(url_for("auth.login"))


@auth_bp.route("/auth/google/callback")
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        current_app.logger.exception("Google OAuth callback failed")
        flash("Google 인증을 완료하지 못했습니다. 다시 시도해 주세요.")
        return redirect(url_for("auth.login"))

    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").strip().lower()
    google_sub = userinfo.get("sub")
    email_verified = userinfo.get("email_verified")

    if not email or not google_sub or email_verified is not True:
        flash("구글 계정 정보를 가져오지 못했습니다.")
        return redirect(url_for("auth.login"))

    account = AuthAccount.query.filter_by(provider="GOOGLE", google_sub=google_sub).first()
    if account is not None:
        account.last_login_at = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to update Google login time")
            flash("Google 로그인 정보를 저장하지 못했습니다. 다시 시도해 주세요.")
            return redirect(url_for("auth.login"))
        login_user(account.user)
        return redirect(url_for("pages.index"))

    user = User.query.filter_by(email=email).first()
    if user is not None:
        linked_google = AuthAccount.query.filter_by(
            user_id=user.id,
            provider="GOOGLE",
        ).first()
        if linked_google is not None:
            flash("이 이메일에는 다른 Google 계정이 이미 연결되어 있습니다.")
            return redirect(url_for("auth.login"))

    try:
        if user is None:
            nickname = (userinfo.get("name") or email.split("@")[0]).strip()[:50]
            if not nickname:
                nickname = f"google-{google_sub[-6:]}"
            if User.query.filter_by(nickname=nickname).first():
                suffix = f"-{google_sub[-6:]}"
                nickname = f"{nickname[:50 - len(suffix)]}{suffix}"
            user = User(email=email, nickname=nickname)
            db.session.add(user)
            db.session.flush()

        account = AuthAccount(
            user_id=user.id,
            provider="GOOGLE",
            google_sub=google_sub,
            last_login_at=datetime.now(timezone.utc),
        )
        db.session.add(account)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.warning("Google account link conflict", exc_info=True)
        flash("Google 계정 연결이 충돌했습니다. 다시 로그인해 주세요.")
        return redirect(url_for("auth.login"))
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Failed to save Google account")
        flash("Google 로그인 정보를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return redirect(url_for("auth.login"))

    login_user(user)
    return redirect(url_for("pages.index"))
