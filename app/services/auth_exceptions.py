class RegistrationDisabledError(Exception):
    pass


class UserAlreadyExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidPasswordResetTokenError(Exception):
    pass


class OAuthProviderNotSupportedError(Exception):
    pass


class OAuthStateInvalidError(Exception):
    pass


class OAuthConfigurationError(Exception):
    pass
