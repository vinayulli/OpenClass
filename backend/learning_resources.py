"""Curated reference URLs; models select resource IDs rather than invent links."""
def for_course(course):
    resources = [{"id": "course:"+m["id"], "title": m["title"], "url": "/courses/"+course["id"]+"/curriculum", "kind": "course", "concept_ids": [c["id"] for c in course["concepts"]]} for m in course.get("materials", [])]
    if "python" in course.get("name", "").lower():
        for concept, title, path in [
            ("functions", "Python tutorial: defining functions", "tutorial/controlflow.html#defining-functions"),
            ("parameters", "Python tutorial: function arguments", "tutorial/controlflow.html#more-on-defining-functions"),
            ("encapsulation", "Python tutorial: private variables and conventions", "tutorial/classes.html#private-variables"),
            ("composition", "Python tutorial: classes and instances", "tutorial/classes.html"),
            ("testing", "Python unittest: basic example", "library/unittest.html#basic-example"),
        ]:
            if concept in {c["id"] for c in course["concepts"]}:
                resources.append({"id": "python:"+concept, "title": title, "url": "https://docs.python.org/3/"+path, "kind": "official_documentation", "concept_ids": [concept]})
    if "machine learning" in course.get("name", "").lower():
        topics = {"ml-workflow":"getting_started.html", "data-quality":"modules/impute.html", "descriptive-statistics":"modules/preprocessing.html", "probability":"modules/calibration.html", "train-test-split":"modules/cross_validation.html", "preprocessing":"modules/preprocessing.html", "linear-regression":"modules/linear_model.html", "regression-metrics":"modules/model_evaluation.html", "logistic-regression":"modules/linear_model.html#logistic-regression", "classification-metrics":"modules/model_evaluation.html", "knn":"modules/neighbors.html", "decision-trees":"modules/tree.html", "cross-validation":"modules/cross_validation.html", "regularization":"modules/linear_model.html#ridge-regression-and-classification", "ensembles":"modules/ensemble.html", "feature-selection":"modules/feature_selection.html", "clustering":"modules/clustering.html", "pca":"modules/decomposition.html#pca", "neural-networks":"modules/neural_networks_supervised.html", "model-deployment":"model_persistence.html"}
        for c in course["concepts"]:
            if c["id"] in topics:
                resources.append({"id":"sklearn:"+c["id"], "title":"scikit-learn guide: "+c["name"], "url":"https://scikit-learn.org/stable/"+topics[c["id"]], "kind":"official_documentation", "concept_ids":[c["id"]]})
    return resources
