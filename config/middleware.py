class AuthenticatedSessionTimeoutMiddleware:
    timeout_seconds = 5 * 60

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            request.session.set_expiry(self.timeout_seconds)
        return response
