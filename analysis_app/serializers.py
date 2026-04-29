from rest_framework import serializers


class AnalyzeRequestSerializer(serializers.Serializer):
    period = serializers.IntegerField(required=False, default=1, min_value=1, max_value=365)
    normalization = serializers.ChoiceField(required=False, default="zscore", choices=["zscore"])
    entity = serializers.CharField(required=False, allow_blank=True)

    include_prompt = serializers.BooleanField(required=False, default=True)
    top_pairs = serializers.IntegerField(required=False, default=10, min_value=1, max_value=50)
    top_freqs = serializers.IntegerField(required=False, default=5, min_value=1, max_value=10)

    return_mode = serializers.ChoiceField(
        required=False,
        default="summary",
        choices=["summary", "entity", "export"],
    )

    summary_top_pairs = serializers.IntegerField(
        required=False,
        allow_null=True,
        default=None,
        min_value=1,
        max_value=10,
    )