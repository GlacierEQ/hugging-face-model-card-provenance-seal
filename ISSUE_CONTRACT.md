# Issue contract — Model Card Provenance Seal

## Problem
Efficient, predictable, safe discovery and use of open AI artifacts.

## Desired outcome
A bounded, open, testable implementation of **Model Card Provenance Seal** that demonstrates Seal model weights + card fields under a content hash and refuse unsealed promotion.

## Non-goals
- Hugging Face affiliation or proprietary integration
- Portfolio-wide scale/performance claims
- UI marketing site

## Acceptance
1. Mechanism module implements allow + refuse with structured receipts
2. pytest behavioral suite green
3. operate.py cold-start produces JSON receipt
4. Non-affiliation disclaimer preserved
