from rest_framework.throttling import UserRateThrottle


class WizardCloudRunBurstRateThrottle(UserRateThrottle):
    scope = "wizard_run_cloud_burst"
    rate = "2/hour"


class WizardCloudRunSustainedRateThrottle(UserRateThrottle):
    scope = "wizard_run_cloud_day"
    rate = "5/day"
