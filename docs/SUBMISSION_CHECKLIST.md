# Hack for Social Cause 2027 submission checklist

Checked against the official [MY Bharat Hack for Social Cause page](https://mybharat.gov.in/pages/hack-for-social-cause) on **11 October 2026**. Requirements and dates can change; confirm the portal before uploading. The page lists **15 October 2026** as the submission deadline.

## Required package

- [ ] **6–7 slide deck**, PPT or PDF, maximum 10 MB, using the IIT Bombay template from the HSC submission page.
- [ ] Cover problem definition and beneficiaries/gaps (slides 1–2), solution (3–4), impact and scalability (5), team/implementation and AI-use disclosure (6–7).
- [ ] **AI-use disclosure** in the deck: explain where AI tools assisted and estimate the share of the final work that involved AI assistance or generated content. Be accurate; do not imply the map assistant is a trained model.
- [ ] **Demo video** (preferred, not mandatory): 3–5 minutes, MP4/MOV, at least 720p, maximum 80 MB; show the team, local problem, working interaction, and intended impact.
- [ ] **Public source repository** (GitHub or GitLab) with complete source, detailed README/setup, architecture, sample data or test cases, and license information. The repository and prototype are linked from the README.
- [ ] **Team details, self-certification, and ID proof (Annexure 1):** all member details, signed declaration, self-attested student ID for each member, and the government-ID details requested in the official form. The team lead uploads the package.
- [ ] Name uploaded files using `<State>_<TeamName>_<Document Name>.pdf`.
- [ ] Confirm every participant has registered individually and the team lead has registered the team on the MY Bharat portal.

## Project items prepared in this repository

- [x] Public GitHub repository and live prototype links in the README.
- [x] Project overview, setup steps, architecture, feature explanations, and limitations.
- [x] MIT license for original project code/documentation.
- [x] Provenance registry, sample local data, and deterministic backend tests.
- [x] Judge walkthrough and test guide: [`JUDGE_GUIDE.md`](JUDGE_GUIDE.md).
- [x] Prepare a 7-slide pitch-content draft: [`BharatYantra_HSC2027_Pitch_Draft.pptx`](submission/BharatYantra_HSC2027_Pitch_Draft.pptx). It is not yet in the official IIT Bombay template; use the portal template before uploading.
- [x] Prepare a 3–5 minute walkthrough script: [`DEMO_VIDEO_SCRIPT.md`](DEMO_VIDEO_SCRIPT.md).
- [ ] Enter the actual team names and roles, and confirm the AI-use percentage in the pitch draft.
- [ ] Transfer the pitch content to the official template and export under 10 MB.
- [ ] Record, review, and upload the demo video.
- [ ] Complete and upload Annexure 1 and each member's required ID documents.
- [ ] Verify data publication rights before presenting the checked-in data bundle as cleared or encouraging redistribution. Current registry status is `hold` for all 19 records; the MIT code license does not cover third-party data. See the README's [data and responsible use section](../README.md#data-and-responsible-use).
- [ ] Re-open the public demo and repository from a signed-out/private browser window immediately before submission.
- [ ] Submit the final package through the MY Bharat portal and save the submission confirmation.

## Suggested deck story

1. **Local problem:** ward teams need to compare preparedness choices using fragmented local map evidence; explain the F/S Ward testbed is provisional.
2. **Who benefits and current gap:** municipal planners and emergency-preparedness teams need inspectable, map-linked scenario comparisons; distinguish the prototype from official systems.
3. **Bharat Yantra:** a map-based decision laboratory connecting scenario inputs, mapped evidence, and review tasks.
4. **Working prototype:** show rainfall inspection shortlist, road-closure access comparison, facility access routes, and budget candidate locations.
5. **Impact and scale:** describe the intended workflow value and a validation-led path to another ward; present no unmeasured savings or lives protected as achieved results.
6. **Build and evidence:** architecture, test coverage, what is deterministic, data limitations, validation still required, deployment link.
7. **Team and AI disclosure:** team roles/plan, AI-tool use and estimated contribution, next validation steps, demo and repository links.
