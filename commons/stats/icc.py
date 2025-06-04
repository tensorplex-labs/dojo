# Import libraries
import pandas as pd
import pingouin as pg
from loguru import logger


def calculate_icc(hotkey_to_scores: dict[str, list[float]]) -> dict[str, float]:
    """Calculate ICC for each rater against the mean of all other raters

    Args:
        hotkey_to_scores (dict[str, list[float]]): Dictionary of miner hotkeys to their miner scores.
        NOTE: the ordering of miner scores should be handled outside this function!

    Returns:
        dict[str, float]: Dictionary of hotkeys to ICC scores
    """

    # Convert to DataFrame
    df = pd.DataFrame(hotkey_to_scores)

    # List of all raters, this would be hotkeys of miners
    raters = list(hotkey_to_scores.keys())

    # Dictionary to store ICC scores
    hotkey_to_icc2 = {}

    # Loop through each rater
    rater_key = "Rater"
    subject_key = "Subject"
    rating_key = "Rating"
    for rater in raters:
        if not is_valid_rater(rater_scores=df[rater], rater_name=rater):
            hotkey_to_icc2[rater] = 0.0
            continue

        # Calculate mean of all other raters (excluding the current rater)
        # we do this to ensure that the current rater is not compared to itself
        other_raters = [r for r in raters if r != rater]
        mean_key = f"Mean_excluding_{rater}"
        df[mean_key] = df[other_raters].mean(axis=1)

        # Subset data for the current rater and the mean of others
        pair_df = df[[rater, mean_key]]

        # Reshape to long format for ICC
        pair_long = pair_df.reset_index().melt(
            id_vars=["index"], var_name=rater_key, value_name=rating_key
        )
        pair_long.columns = [subject_key, rater_key, rating_key]

        # Calculate ICC (using ICC2 for two-way random effects, absolute agreement)
        icc_result = pg.intraclass_corr(
            data=pair_long,
            targets=subject_key,
            raters=rater_key,
            ratings=rating_key,
        )

        # Extract ICC2 value
        icc_value = icc_result[icc_result["Type"] == "ICC2"]["ICC"].values[0]

        # Store the score
        hotkey_to_icc2[rater] = icc_value
    return hotkey_to_icc2


def has_missing_scores(rater_scores: pd.Series, rater_name: str) -> bool:
    """Check if rater has any missing scores"""
    missing_count = rater_scores.isna().sum()
    if missing_count > 0:
        logger.warning(
            f"{rater_name} has {missing_count} missing scores, assigning ICC = 0.0"
        )
        return True
    return False


def has_duplicate_scores(rater_scores: pd.Series, rater_name: str) -> bool:
    """Check if rater has any duplicate scores"""
    scores_list = rater_scores.tolist()
    unique_scores = set(scores_list)

    if len(unique_scores) != len(scores_list):
        logger.warning(
            f"{rater_name} has duplicate scores {scores_list}, assigning ICC = 0.0"
        )
        return True
    return False


def is_valid_rater(rater_scores: pd.Series, rater_name: str) -> bool:
    """Combined validation for rater scores"""
    if has_missing_scores(rater_scores, rater_name):
        return False
    if has_duplicate_scores(rater_scores, rater_name):
        return False
    return True


if __name__ == "__main__":
    # Sample data: 5 items rated by 4 raters
    # TODO: hotkey to scores, ensure proper ordering!!!
    data = {
        "Rater1": [34.0, 23.0, 12.0, 45.0],
        "Rater2": [23.0, 45.0, 34.0, 12.0],
        "Rater3": [34.0, 12.0, 23.0, 45.0],
        "Rater4": [34.0, 23.0, 12.0, None],
        "Rater5": [34.0, 45.0, 45.0, 45.0],
        "Rater6": [34.0, 45.0, 45.0, 45.0],
        "Rater7": [34.0, 45.0, 45.0, 45.0],
        "Rater8": [34.0, 45.0, 45.0, 45.0],
        "Rater9": [34.0, 45.0, 45.0, 45.0],
        "Rater10": [34.0, 45.0, 45.0, 45.0],
    }

    # icc_scores = calculate_icc(data)
    # # Display the results
    # print("Inter-Rater Reliability (ICC) Scores:")

    # for pair, score in icc_scores.items():
    #     print(f"{pair}: ICC = {score:.3f}")
