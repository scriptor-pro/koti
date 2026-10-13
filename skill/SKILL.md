---
name: koti
description: Affiche les tâches quotidiennes (rituels) suivies par koti sous forme de liste à cocher, avec leurs séries, et coche celles que l'utilisateur déclare faites. À utiliser quand l'utilisateur tape /koti, demande sa liste de tâches quotidiennes / du jour / ses rituels, ou déclare avoir fait une de ses tâches quotidiennes.
---

# koti — liste à cocher des tâches quotidiennes

Tout passe par la commande `koti` (dans le PATH, utilisable depuis n'importe quel dossier). Ne jamais modifier `completions.csv` à la main pour cocher une tâche : `koti fait` ajoute la ligne au journal, puis régénère et publie la page une seule fois.

## Sans argument : afficher puis proposer de cocher

1. Lancer `koti` et recopier la liste telle quelle dans la réponse (☑ faite, ☐ à faire), pour que l'utilisateur la voie en entier.
2. Les tâches cochables sont les lignes ☐ **sans** la mention « pas avant HH:MM ». Ne jamais proposer une tâche portant cette mention.
3. S'il reste des tâches cochables, les proposer avec `AskUserQuestion` en `multiSelect: true` :
   - une option par tâche, libellé = titre court, description = identifiant ;
   - 4 options au plus par question, donc répartir sur plusieurs questions si nécessaire ;
   - une question exige au moins 2 options : s'il ne reste qu'une tâche, poser une question simple « Fait » / « Pas encore ».
4. Lancer `koti fait ID [ID ...]` avec toutes les tâches cochées, en une seule commande. Si rien n'est coché, ne rien lancer.
5. Relancer `koti` et afficher la liste à jour.

S'il ne reste rien à cocher, afficher la liste et le dire, sans poser de question.

Certains rituels sont suivis « sans série » : leur ligne affiche un nombre de sessions au lieu d'une série, et ils ne comptent pas dans « N sur M faites » ; ils se cochent comme les autres.

## Avec arguments

`/koti lecture marche` ou « j'ai fait la lecture et la marche » : cocher directement, sans questionnaire, en passant les identifiants affichés par `koti`. Si la commande répond « Nom ambigu » ou « Tâche inconnue », rien n'a été écrit : demander à l'utilisateur de quelle tâche il s'agit. Puis afficher la liste à jour.

## Heure et date

Par défaut la commande inscrit la date du jour et l'heure de déclaration. L'heure sert à calculer l'heure moyenne de chaque rituel :

- si l'utilisateur précise une heure (« à 8 h 15 »), ajouter `--heure HH:MM` ; si les heures diffèrent d'une tâche à l'autre, lancer une commande par heure ;
- pour un jour passé (« hier », déclaration après minuit), ajouter `--date AAAA-MM-JJ`, et `--heure` seulement si l'utilisateur la donne.

## Cas limites de la date et de l'heure

- une date future (`--date`) est refusée : rien n'est écrit ;
- `--date` sans `--heure` inscrit une heure vide (la complétion compte pour la série, pas pour l'heure moyenne) ;
- la règle « pas avant HH:MM » (heure fixe) est comparée à l'heure actuelle de l'horloge, même quand `--heure` est donnée ; elle ne s'applique pas à une `--date` passée.

## Publication

La page est publiée à chaque cochage. N'ajouter `--no-upload` que sur consigne explicite dans le message en cours.

`koti page` régénère la page sans rien cocher, puis la publie (`--no-upload` pour ne pas publier, seulement sur consigne explicite).

## Quand `koti fait` se termine en erreur (code 1)

- **Échec de publication** : si la sortie contient des lignes `OK — … cochée` suivies d'une ligne `ERREUR — …` (sur la sortie d'erreur), le cochage EST enregistré dans le journal. Ne pas relancer `koti fait` : il répondrait « IGNORÉE » puis « Rien à cocher » et ne republierait rien. Lancer `koti page` pour régénérer et republier, et signaler l'erreur à l'utilisateur si elle persiste.
- **« Rien à cocher — aucun fichier modifié. »** avec uniquement des lignes `IGNORÉE` (déjà cochée) ou `REFUSÉE` (heure fixe non atteinte) : ce n'est pas une panne mais une issue normale. Le rapporter tel quel, sans réessayer.

## Compte rendu

Rapporter ce que la commande a réellement affiché : tâches cochées, tâches ignorées (déjà cochées) ou refusées (heure fixe non atteinte), résultat de la publication et URL signée.
