
import json

from intelligence.context_engine import generate_context_output


def main():

    input_path = "temp/scene_analysis.json"

    with open(input_path, "r", encoding="utf-8") as file:
        scene_analysis = json.load(file)

    result = generate_context_output(scene_analysis)

    print("\n========== CONTEXT ENGINE OUTPUT ==========\n")

    print(json.dumps(result, indent=4, ensure_ascii=False))

    output_path = "temp/sound_context.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            result,
            file,
            indent=4,
            ensure_ascii=False
        )

    print(f"\nContext saved to: {output_path}")


if __name__ == "__main__":
    main()
