"""Stateless column-mapping helpers used by Evidently analysis."""


def filter_column_mapping(column_mapping, common_cols, mapping_factory):
    common_set = set(common_cols)
    filtered_mapping = mapping_factory()
    if column_mapping.numerical_features:
        filtered_mapping.numerical_features = [
            column for column in column_mapping.numerical_features if column in common_set
        ]
    if column_mapping.categorical_features:
        filtered_mapping.categorical_features = [
            column for column in column_mapping.categorical_features if column in common_set
        ]
    if getattr(column_mapping, "target", None) in common_set:
        filtered_mapping.target = column_mapping.target
    if getattr(column_mapping, "prediction", None) in common_set:
        filtered_mapping.prediction = column_mapping.prediction
    return filtered_mapping
