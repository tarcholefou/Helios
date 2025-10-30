diff --git a/README.md b/README.md
index 618f8608fc46caf0ffe11b537c8acff32a7a833d..7daba127e146e51c3fa425fac29525c981d1a2b5 100644
--- a/README.md
+++ b/README.md
@@ -1 +1,99 @@
 # Helios
+
+Application Streamlit pour piloter les données de ventes d'une salle de CrossFit.
+
+## Fonctionnalités
+
+- Import de fichiers **Excel**, **CSV** et **PDF** contenant vos ventes (abonnements et boutique) via un simple glisser-déposer.
+- Analyse des relevés PDF même sans tableaux structurés grâce à un parsing heuristique (dates, libellés, montants).
+- Normalisation automatique des colonnes (dates, montants, catégories) et agrégations par mois.
+- Tableau de bord interactif avec un écran d'accueil visuel, des indicateurs clés et des onglets pour naviguer entre graphiques et tableaux.
+- Comparaison mois par mois avec calcul des variations en pourcentage.
+- Génération optionnelle d'un résumé automatique grâce à l'API OpenAI.
+
+## Prise en main
+
+1. Installez les dépendances :
+
+   ```bash
+   pip install -r requirements.txt
+   ```
+
+2. Lancez l'application Streamlit :
+
+   ```bash
+   streamlit run app.py
+   ```
+
+   ou simplement :
+
+   ```bash
+   python app.py
+   ```
+
+   (la commande démarre automatiquement Streamlit si vous ne souhaitez pas utiliser le CLI dédié).
+
+3. Téléversez vos exports de ventes (formats `.xlsx`, `.xls`, `.csv` ou `.pdf`). L'outil accepte à la fois le glisser-déposer et
+   la boîte de dialogue classique ; une fois le fichier déposé il apparaît dans la liste avec un message de confirmation. Si le
+   document est un PDF, sa première page est immédiatement analysée pour récupérer le tableau de chiffre d'affaires.
+4. Filtrez par mois et par catégorie, explorez les graphiques et consultez les tableaux de synthèse.
+5. (Optionnel) Saisissez votre clé API OpenAI dans la barre latérale puis activez l'analyse IA pour obtenir un résumé intelligent des performances.
+
+## Mettre à jour votre installation
+
+Pour bénéficier des dernières évolutions (dont la prise en charge des PDF en glisser-déposer), assurez-vous de synchroniser votre copie locale :
+
+```bash
+git pull
+pip install -r requirements.txt
+streamlit cache clear  # facultatif mais utile après une grosse mise à jour
+streamlit run app.py
+```
+
+- `git pull` récupère la version la plus récente du projet.
+- `pip install -r requirements.txt` garantit que les bibliothèques nécessaires, notamment `pdfplumber` pour les PDF, sont bien installées ou mises à jour.
+- `streamlit cache clear` supprime les fichiers mis en cache afin que l'interface se recharge sans reliquats d'une ancienne version.
+- Redémarrez ensuite l'application Streamlit (`Ctrl+C` puis relancez la commande) pour prendre en compte les modifications.
+
+Si vous utilisez l'application en production (par exemple sur Streamlit Cloud), redéployez ou redémarrez le service après avoir mis à jour le dépôt afin d'appliquer les changements.
+
+## Vérifier que vous exécutez la dernière version
+
+- Dans l'application, la bannière d'accueil affiche désormais un badge « Version installée ». Le texte doit correspondre à la version que vous venez de déployer (par exemple `Helios 0.3.0 (abc1234)`). Si la version ne change pas, forcez l'actualisation de votre navigateur (⌘/Ctrl + Shift + R) ou redémarrez la session Streamlit.
+- En ligne de commande, vous pouvez vérifier la dernière révision récupérée avec :
+
+  ```bash
+  git log -1 --oneline
+  ```
+
+  La valeur affichée doit correspondre au hash court indiqué dans l'interface.
+- Si l'ancienne interface persiste malgré tout, supprimez le cache de Streamlit (`streamlit cache clear`) et assurez-vous qu'aucun autre serveur `streamlit run` n'est resté actif en arrière-plan.
+
+## À quoi ressemble la nouvelle interface ?
+
+- L'arrière-plan adopte un dégradé bleu/violet et une bannière « Nouvelle interface » apparaît en haut de page.
+- Trois cartes récapitulatives « 1. Déposer », « 2. Filtrer », « 3. Analyser » sont affichées sous la bannière d'accueil pour guider la prise en main.
+- La mention « Drag & drop activé pour les relevés PDF » figure dans la bannière, suivie du badge de version Helios.
+
+Si votre écran d'accueil n'affiche pas ces éléments, vous consultez encore une ancienne révision. Dans ce cas, répétez la procédure de mise à jour ci-dessus (pull Git, installation des dépendances, suppression du cache Streamlit puis redémarrage de l'application).
+
+## Structure du projet
+
+- `app.py` : application Streamlit.
+- `helios/data_loader.py` : chargement de fichiers et extraction PDF.
+- `helios/data_processing.py` : nettoyage, normalisation et agrégations.
+- `helios/visualization.py` : graphiques Plotly.
+- `helios/ai_assistant.py` : intégration avec l'API OpenAI.
+
+## Configuration OpenAI
+
+Définissez la variable d'environnement `OPENAI_API_KEY` ou renseignez votre clé dans l'interface Streamlit pour activer les fonctionnalités IA. Le modèle utilisé par défaut est `gpt-4o-mini` mais vous pouvez le modifier dans la barre latérale.
+
+## Notes sur les PDF
+
+L'import de fichiers PDF repose sur la bibliothèque `pdfplumber`. Helios inspecte prioritairement la première page du document,
+ce qui permet d'exploiter immédiatement un glisser-déposer du « recto » du relevé. En l'absence de tableau ou de lignes
+structurées sur la première page, l'application retente automatiquement sur l'ensemble du document. Helios applique ensuite un
+parsing heuristique des lignes textuelles (dates, libellés, montants) pour traiter les relevés comptables mensuels dépourvus de
+tableaux structurés. Les PDF scannés sans texte sélectionnable restent incompatibles : dans ce cas, privilégiez un export
+Excel/CSV.
