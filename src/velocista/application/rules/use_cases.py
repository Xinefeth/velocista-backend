from velocista.application.rules.ports import RulesRepository
from velocista.domain.shared.errors import NotFound


class RulesService:
    def __init__(self, repository: RulesRepository):
        self.repository = repository

    def list_profiles(self):
        return self.repository.list_profiles()

    def get_profile(self, profile_id):
        profile = self.repository.get_profile(profile_id)
        if profile is None:
            raise NotFound("profile_not_found", "Profile does not exist")
        return profile
