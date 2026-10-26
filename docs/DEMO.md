# New complaint demonstration

Start the application as described in README. The quickest path is the built-in
guided tour (**Take the guided tour** on the entry page), which walks this whole
flow with explanations; the steps below are the same flow without the tour. Open two browser tabs on the same
origin so the synthetic practice-session cookie scopes both victim and analyst.
Do not start from a preloaded complaint.

1. Open `/app/#/victim/start`. Choose **when the scam payment happened** (10 or 40
   minutes ago is inside the golden hour; 2 hours ago has missed it) and click
   **Start a fresh practice session**. A new fictional bank, customers, scam payment
   and onward money movements are generated now, timed to your choice, with an
   empty queue. Customers holding the scam payment are marked; the first is selected.
2. Choose a synthetic customer and **Continue with selected customer**. Open
   `/app/#/staff/queue` in the second tab; the practice queue should be empty.
3. In the victim tab choose **Report a payment scam**. Select the suspicious
   payment, continue, and describe what you know. Unknown details can stay unknown.
4. Download **View bank receipt**, then upload that actual PNG using **Report
   evidence**. A personally created supported PNG/JPEG/text file can also be used;
   extraction and source checks still apply. Continue and **Submit report**.
5. Wait for processing. The analyst queue receives a newly created case ID.
   Open it, review payment inventory, evidence citations and money trail. Local
   processing uses actual OCR plus literal rules; live Google AI is not enabled.
6. Use **Requests → Review & send → Confirm request** for the supported missing
   information. Open the scoped reply link and submit the requested explanation.
   If an additional debit is shown, explicitly confirm or deny its relationship.
7. Wait for a new assessment revision. Review the investigation brief and readiness
   gaps. Choose the reviewer demo persona, provide an approval reason and approve
   the current revision. Do not override unexplained conflicts just to finish.
8. Send the handoff. Verify both delivery acknowledgements, then open **View
   delivered report**: the exact report both receivers got (bank case ticket and
   cybercrime report update), printable as a PDF. Set the follow-up owner and next
   action. Delivered does not mean recovered or closed.
9. Reload both tabs to confirm persistence. Repeat with a different customer and
   new complaint. Uploaded evidence and replies must produce their own results.

The two receivers emulate a bank case system and CFCFRMS-style report destination.
They do not contact banks, file official reports, freeze funds or recover money.
Local role switching is a labeled demonstration mechanism, not production login.

If a job fails, retain the visible error and retry after resolving its cause.
Do not claim that a pending/error case is fully assessed. The bank-data freshness
indicator may trigger a background refresh; normal users need not open a simulator.
