# Ρώτησε τον Δήμο σου

Εργαλείο διαφάνειας του Urban Policy Lab (Πυλώνες 1 και 4) για τις απευθείας αναθέσεις των δήμων.

- **Σκέλος Α (Εικόνα):** δείκτες από το Open Data API του ΚΗΜΔΗΣ, μόνο συγκεντρωτικά ανά δήμο.
- **Σκέλος Β (Ερώτηση):** έτοιμο αίτημα πρόσβασης (άρθρο 5 ν. 2690/1999, όπως ισχύει μετά το άρθρο 59 ν. 5143/2024) που υπογράφει ο πολίτης μέσω gov.gr.

## Πώς λειτουργεί
| Μέρος | Αρχείο | Τι κάνει |
|---|---|---|
| ETL | `etl/build.py`, `etl/khmdhs.py` | Ανακτά τις συμβάσεις 12 μηνών ανά δήμο, γράφει `site/data/indicators.json` |
| Πιλοτικοί δήμοι | `etl/pilot.json` | 14 δήμοι, κωδικοί φορέα ΚΗΜΔΗΣ, email πρωτοκόλλου |
| Σελίδα | `site/index.html` | Στατική σελίδα, διαβάζει τα JSON |
| Μητρώο | `site/data/requests.json` | Αιτήματα και απαντήσεις, χωρίς στοιχεία πολιτών |
| Αυτοματισμός | `.github/workflows/update.yml` | Κάθε Δευτέρα: ETL, commit, δημοσίευση σε GitHub Pages |

## Εκκίνηση
1. Δημόσιο αποθετήριο GitHub (λογαριασμός UPL), ανέβασμα του φακέλου.
2. Settings → Pages → Source: GitHub Actions.
3. Actions → update-and-deploy → Run workflow.
4. Προαιρετικά: υποτομέας `rotise.urbanpolicylab.org` (CNAME).

Τοπικά: `cd etl && python build.py`, μετά `cd site && python -m http.server`.

## Μητρώο αιτημάτων
Κάθε εγγραφή: `{"municipality":"athina","question":"market","sent_date":"2026-12-01","protocol_no":"…","answered_date":null,"status":"pending"}`.
Δεν καταχωρίζονται ονόματα ή στοιχεία πολιτών.

## Άδειες
Δεδομένα ΚΗΜΔΗΣ: CC BY 4.0. Κώδικας: προτείνεται MIT.
