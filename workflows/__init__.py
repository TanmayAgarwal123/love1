"""The seven workflow modules. Each is independently toggled in config.yaml
(workflows.<name>.enabled) and independently flipped live (workflows.<name>.live)."""
from . import date_night, friends_crm, gift_list, long_shift, random_flowers, referee, reply_monitor

REGISTRY = {m.NAME: m for m in (reply_monitor, gift_list, date_night, friends_crm, long_shift, random_flowers, referee)}
ORDER = list(REGISTRY)
INVOKE_ONLY = {"referee"}
