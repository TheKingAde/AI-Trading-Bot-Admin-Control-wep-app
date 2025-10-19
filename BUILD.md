FRONTEND FIXES

ALL SECTION CONTENTS SHOULD ALWAYS BE CONTAINED IN THEIR SECTION BOX AND NOT OVERFLOW
THE LIVE RADES SECTION TABLE IS OVERFLOWING


PERFORMANCE BY PAIR SECTION UPDATE:
I WANT TO BE ABLE TO CHOOSE WHICH PAIR TO VIEW IT'S PERFMANNCE AND THE PEFROMANCE SHOULD BE PLOTTED AS A PIE CHART/HISTOGRAM//CURVE WITH APPROPRAITE LABELS ALONG WITH THE 
CONTAINED TABLE


Fix the issue where, when the admin selects any of the actions (Activate License, Deactivate License, Renew License, Check Status), all input fields are displayed at once. They should instead be displayed as follows:

- **Activate License:** show input fields for `key`, `name`, and `number of days`.
- **Deactivate License:** show input field for `key` only.
- **Renew License:** show input fields for `key` and `number of days`.
- **Check Status:** show input field for `key` only.

Do not make any other changes.