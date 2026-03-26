import argparse
import warnings

from scipy.sparse.linalg import MatrixRankWarning

import member_database as mdb
from portal_frame_analysis import import_data, build_model


def analyze_pair(r_mem, c_mem, data) -> str:
    """Return status for a section pair: ok, singular, or error."""
    frame = build_model(r_mem, c_mem, data)

    for combo in data.serviceability_load_combinations:
        frame.add_load_combo(combo["name"], combo["factors"])
    for combo in data.load_combinations:
        frame.add_load_combo(combo["name"], combo["factors"])

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("error", category=MatrixRankWarning)
            frame.analyze(check_statics=False)
        return "ok"
    except MatrixRankWarning:
        return "singular"
    except Exception:
        return "error"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find section pairs that cause singular matrix warnings."
    )
    parser.add_argument("--rafter-type", default="I-Sections")
    parser.add_argument("--column-type", default="I-Sections")
    parser.add_argument("--preferred", default="Yes")
    args = parser.parse_args()

    member_db = mdb.load_member_database()
    data = import_data("input_data.json")

    r_list = [
        sec
        for sec in member_db[args.rafter_type]
        if member_db[args.rafter_type][sec].get("Preferred", "No") == args.preferred
    ]
    c_list = [
        sec
        for sec in member_db[args.column_type]
        if member_db[args.column_type][sec].get("Preferred", "No") == args.preferred
    ]

    if not r_list or not c_list:
        raise ValueError(
            f"No sections found for Preferred='{args.preferred}' in "
            f"{args.rafter_type}/{args.column_type}."
        )

    singular = []
    errored = []
    total = len(r_list) * len(c_list)
    done = 0

    for r_name in r_list:
        for c_name in c_list:
            done += 1
            r_mem = mdb.member_properties(args.rafter_type, r_name, member_db)
            c_mem = mdb.member_properties(args.column_type, c_name, member_db)
            status = analyze_pair(r_mem, c_mem, data)

            if status == "singular":
                singular.append((r_name, c_name))
            elif status == "error":
                errored.append((r_name, c_name))

            if done % 25 == 0 or done == total:
                print(f"Checked {done}/{total} pairs...")

    print("\nSingular section pairs:")
    if singular:
        for r_name, c_name in singular:
            print(f"- Rafter={r_name}, Column={c_name}")
    else:
        print("- None")

    print("\nPairs with other errors:")
    if errored:
        for r_name, c_name in errored:
            print(f"- Rafter={r_name}, Column={c_name}")
    else:
        print("- None")


if __name__ == "__main__":
    main()
