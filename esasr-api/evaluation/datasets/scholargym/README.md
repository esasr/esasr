---
license: apache-2.0
task_categories:
  - text-retrieval
  - question-answering
language:
  - en
tags:
  - deep-research
  - academic-literature
  - benchmark
  - information-retrieval
  - multi-turn
pretty_name: ScholarGym
size_categories:
  - 100K<n<1M
---

# ScholarGym: Benchmarking Deep Research Workflows on Academic Literature Retrieval

## Dataset Description

ScholarGym is a static evaluation environment for reproducible assessment of deep research workflows
on academic literature retrieval. It provides a unified benchmark with expert-annotated queries over
a static corpus of 570K papers with deterministic retrieval.

- **Paper:** [arXiv:2601.21654](https://arxiv.org/abs/2601.21654)
- **GitHub:** [https://github.com/shenhao-stu/ScholarGym](https://github.com/shenhao-stu/ScholarGym)

### Dataset Components

**1. scholargym_bench (Query Benchmark)**
- 2,536 expert-annotated research queries
- Sourced from PaSa (AutoScholar + RealScholar) and LitSearch datasets
- Each query includes ground-truth relevant papers with arXiv IDs
- Partitioned into:
  - Test-Fast: 200 queries for rapid development iteration
  - Test-Hard: 100 challenging queries requiring cross-area retrieval

**2. scholargym_paper_db (Paper Corpus)**
- 570K academic papers spanning computer science, physics, and mathematics
- Enriched with arXiv metadata (title, abstract, publication date, authors)
- Deduplicated by arXiv identifier
- Supports deterministic retrieval for reproducible evaluation

## Usage

```python
from datasets import load_dataset

# Load query benchmark
dataset = load_dataset("shenhao/ScholarGym", name="benchmark")

# Load paper corpus (sample)
papers = load_dataset("shenhao/ScholarGym", name="papers")
```

## Citation

```bibtex
@article{shen2026scholargym,
  title={ScholarGym: Benchmarking Large Language Model Capabilities in the Information-Gathering Stage of Deep Research},
  author={Shen, Hao and Yang, Hang and Gu, Zhouhong},
  journal={arXiv preprint arXiv:2601.21654},
  year={2026}
}
```

## License

This dataset is released under the Apache License 2.0.

## Acknowledgments

We thank the authors of [PaSa](https://github.com/bytedance/pasa) and [LitSearch](https://github.com/princeton-nlp/LitSearch) for providing the base datasets that enabled the construction of ScholarGym.