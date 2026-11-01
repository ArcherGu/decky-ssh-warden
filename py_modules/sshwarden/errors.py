class UserError(Exception):
    """An error meant for the user.

    The panel translates it by `code` (see `errors` in src/i18n.ts) and fills in `params`;
    the English message is what logs and the command-line tool show.
    """

    def __init__(self, code: str, message: str, **params):
        super().__init__(message.format(**params))
        self.code = code
        self.params = params
