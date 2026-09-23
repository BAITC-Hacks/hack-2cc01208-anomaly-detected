# Literature Review — Why This Architecture

Four narrowing steps, six real sources, each checked for a resolvable DOI/URL and real author names before being cited — nothing here is taken from a search-engine summary alone.

1. **Recommending service providers in two-sided marketplaces is a studied, economically real problem**, not a toy exercise: Shi (2024) derives the optimal match-recommendation policy for platforms structurally identical to this one — a customer picks from a short list of service providers (Shi, 2024).
2. **Thin, attribute-rich data calls for constraint-based reasoning, not collaborative filtering.** We have 66 profiles and no interaction history. Knowledge-based and constraint-based recommenders were built for exactly this regime, and critically, they can **explain a recommendation even when no item satisfies the constraints** (Burke, 2000; Felfernig & Burke, 2008) — the direct justification for treating `none_fit`/`no_category` as first-class, explained API states instead of silent empty results.
3. **The event-vendor domain already has prior art, and it skips the explanation.** Singh, Singh, and Bathla (2020) built a hybrid content/social recommender for event planning that scores candidates numerically but does not generate a per-recommendation natural-language justification — exactly the gap this case brief singles out ("the value is in the explanation, not the sorting").
4. **Using an LLM only to explain an already-decided result is still a minority pattern in the literature**, and that's precisely why it needs validation. A 2025 systematic review found only 6 of 232 screened papers actually used an LLM this way (Said, 2025). LLM-generated text is a known hallucination risk in general (Ji et al., 2023) — which is why this system never lets Groq choose or reorder a card; it only rewrites explanation text for cards Python already picked, and that text is checked against real contractor fields before being shown, with an automatic template fallback on any failure.

See the comparison table in the main [README](../README.md#related-work) for how this combination compares to the cited systems directly.

## References (APA 7th edition)

Burke, R. (2000). Knowledge-based recommender systems. In A. Kent (Ed.), *Encyclopedia of library and information systems* (Vol. 69, Suppl. 32, pp. 180–200). Marcel Dekker.

Felfernig, A., & Burke, R. (2008). Constraint-based recommender systems: Technologies and research issues. In *Proceedings of the 10th International Conference on Electronic Commerce*. ACM. https://dl.acm.org/citation.cfm?id=1409544

Ji, Z., Lee, N., Frieske, R., Yu, T., Su, D., Xu, Y., Ishii, E., Bang, Y. J., Madotto, A., & Fung, P. (2023). Survey of hallucination in natural language generation. *ACM Computing Surveys*, *55*(12), Article 248. https://doi.org/10.1145/3571730

Said, A. (2025). On explaining recommendations with large language models: A review. *Frontiers in Big Data*, *7*, Article 1505284. https://doi.org/10.3389/fdata.2024.1505284

Shi, P. (2024). Optimal match recommendations in two-sided marketplaces with endogenous prices. *Management Science*, *71*(9), 7431–7448. https://doi.org/10.1287/mnsc.2022.02691

Singh, R. K., Singh, P., & Bathla, G. (2020). User-review oriented social recommender system for event planning. *Ingénierie des Systèmes d'Information*, *25*(5). https://doi.org/10.18280/isi.250514
