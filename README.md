# KRYPTA

KRYPTA est une application Windows de bureau, en français, pour coder des textes par substitution ou les chiffrer localement. Elle ne demande ni compte, ni serveur, ni service payant. L’interface et les traitements restent sur l’ordinateur.

## Installation

Pré-requis : Python 3.10 ou ultérieur (64 bits recommandé) et Windows 10/11.

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Si PowerShell bloque l’activation de l’environnement, appelez directement les exécutables dans `.venv\Scripts\` ou utilisez l’invite de commandes Windows.

## Lancement

```powershell
.\.venv\Scripts\python.exe main.py
```

Le lanceur Windows `run_krypta.bat` démarre l’application depuis l’environnement `.venv`. Pour conserver les données des versions précédentes, la base locale existante reste dans `%APPDATA%\Ciphera\ciphera.sqlite3` (sur Windows).

## Utilisation

Dans **Coder / Décoder**, collez ou importez un texte, choisissez une action, puis lancez le traitement avec le bouton ou `Ctrl+Entrée`. Les raccourcis `Ctrl+Shift+C` (copier le résultat), `Ctrl+Shift+V` (coller dans la source) et `Ctrl+L` (effacer) sont disponibles. L’interface reste réactive pendant les opérations.

### Substitution

La clé illustrative « Exemple grec — correspondance illustrative » est un exemple pédagogique et non une norme. Dans **Mes clés**, vous pouvez créer, rechercher, modifier, dupliquer, supprimer, importer et exporter des clés JSON.

Chaque caractère source possède un jeton de sortie non vide (jusqu’à 128 caractères). Les caractères qui ne sont pas dans la clé sont échappés et préservés par défaut, ou peuvent être refusés. Le format **avec séparateurs** échappe `|` et `\`. Le format **compact** exige des jetons uniques formant un code préfixe ; les caractères inconnus utilisent une séquence Unicode échappée réservée.

Les modes de casse « commune » et « minuscules » normalisent l’entrée : les majuscules d’origine sont alors perdues et l’interface l’indique. Les collisions rendent une clé non réversible et sont refusées lors du codage/décodage. Les accents, emojis, espaces et retours à la ligne sont traités comme des caractères Unicode.

**Une substitution n’est pas un chiffrement sécurisé.** Elle ne doit pas protéger des données sensibles.

### Chiffrement

Le mode AES utilise AES-256-GCM avec un nonce aléatoire neuf de 12 octets et un sel aléatoire de 16 octets pour chaque chiffrement. Un mot de passe UTF-8 est dérivé par Scrypt (`N=16384`, `r=8`, `p=1`, clé de 32 octets), paramètres documentés et limités afin de prévenir les paramètres coûteux injectés par un fichier malformé. L’enveloppe textuelle versionnée commence par `CIPHERA1:` et transporte les paramètres, le sel, le nonce et le ciphertext authentifié en Base64 URL-safe. Les textes sont limités à 1 Mio d’octets UTF-8.

Le mot de passe n’est jamais enregistré dans la base ni dans l’historique. **Sa perte peut rendre les données irrécupérables.** Un mot de passe erroné ou un message altéré échoue sans résultat partiellement déchiffré.

La couche de substitution optionnelle sur une enveloppe AES est une transformation de présentation uniquement ; elle n’ajoute aucune sécurité cryptographique et la clé doit couvrir tous les caractères de l’enveloppe.

## Stockage et confidentialité

Les clés de substitution et préférences sont enregistrées dans SQLite dans le répertoire de données utilisateur Windows. L’historique est désactivé par défaut. Lorsqu’il est activé, il ne conserve que date UTC, action, mode et nom de clé — jamais les textes, mots de passe ou clés cryptographiques. Il peut être supprimé entrée par entrée ou intégralement.

Les imports JSON sont limités à 1 Mio, validés selon un schéma versionné strict, rejettent les propriétés inattendues/dupliquées et n’exécutent jamais de code. Exporter une clé de substitution ne révèle pas de secret cryptographique ; ne confondez pas cette clé avec un mot de passe AES.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Les tests couvrent les aller-retours Unicode et les formats, les collisions, les imports, SQLite, les enveloppes malformées, mots de passe erronés, modifications du ciphertext, paramètres aléatoires et combinaison des modes.

## Générer l’exécutable Windows

Depuis la racine du projet, après installation des dépendances :

```powershell
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --name KRYPTA main.py
```

Le programme est généré dans `dist\KRYPTA\` (distribution en dossier). Pour produire un exécutable unique, ajoutez `--onefile`. Testez toujours le résultat sur une machine Windows cible ; le premier démarrage peut prendre quelques secondes.

## Dépannage et limites

- Si PySide6 ne s’installe pas, vérifiez que Python est une version 64 bits prise en charge et mettez `pip` à jour.
- En cas d’erreur de lecture/écriture, vérifiez les droits d’accès au dossier `%APPDATA%\Ciphera` (conservé pour compatibilité avec les données déjà créées).
- Une clé dont des jetons se chevauchent ne peut pas être utilisée au format compact ; créez des jetons préfixes distincts ou sélectionnez le format séparé.
- La base locale et les fichiers exportés ne sont pas chiffrés par KRYPTA. Protégez le compte Windows et vos sauvegardes selon vos besoins.
