from fastapi import APIRouter
from pydantic import BaseModel

from offsponsr.auth import AccountService, AccountState


class AccountInfo(BaseModel):
    signed_in: bool
    email: str | None
    # The stored session stopped working; the user has to sign in again.
    expired: bool


class CookieLogin(BaseModel):
    # The `Cookie` request header, as the browser's DevTools show it.
    cookie: str


def _info(state: AccountState) -> AccountInfo:
    return AccountInfo(signed_in=state.signed_in, email=state.email, expired=state.expired)


def account_router(account: AccountService) -> APIRouter:
    router = APIRouter()

    @router.get('/account')
    def status() -> AccountInfo:
        return _info(account.state())

    @router.post('/account/login')
    def login() -> AccountInfo:
        # Answers when the login window closes, so this request can take minutes.
        return _info(account.login_with_window())

    @router.post('/account/login/cookie')
    def login_with_cookie(body: CookieLogin) -> AccountInfo:
        return _info(account.login_with_cookie_header(body.cookie))

    @router.post('/account/logout')
    def logout() -> AccountInfo:
        return _info(account.logout())

    return router
