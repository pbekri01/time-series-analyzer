import math
import json
import os
from urllib import error, request as urlrequest
from django.views.decorators.csrf import ensure_csrf_cookie

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .map_utils import build_map_rows, build_choropleth_html, extract_available_pairs
from .serializers import AnalyzeRequestSerializer
from .services import (
    load_uploaded_csvs,
    run_analysis,
    build_entity_response,
    make_summary_payload,
)
from .exports import make_export_zip_bytes


def _compact_json(obj):
    return json.dumps(_json_safe(obj), ensure_ascii=False, indent=2)


def _build_chat_context_from_result(result):
    if not result:
        return "No analysis has been run yet."

    summary_payload = make_summary_payload(result, summary_top_pairs=3)
    return "\n\n".join([
        "Summary snapshot of the uploaded time-series analysis:",
        _compact_json(summary_payload),
    ])


def _call_openrouter(messages, model):
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()

    payload = {
        "model": model,
        "messages": messages,
    }

    req = urlrequest.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urlrequest.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _chat_completion_openrouter(messages):
    primary = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b:free")
    fallback = os.getenv("OPENROUTER_FALLBACK", "mistralai/mistral-7b-instruct:free")

    try:
        data = _call_openrouter(messages, primary)
    except error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")

        if e.code == 429:
            try:
                data = _call_openrouter(messages, fallback)
            except error.HTTPError as fallback_error:
                fallback_detail = fallback_error.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Primary model was rate-limited and fallback also failed: {fallback_detail}"
                )
        else:
            raise RuntimeError(f"OpenRouter error {e.code}: {detail}")

    if "choices" not in data or not data["choices"]:
        raise RuntimeError(
            f"Unexpected OpenRouter response: {json.dumps(data, ensure_ascii=False)}"
        )

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            "Could not read assistant message from OpenRouter response: "
            f"{json.dumps(data, ensure_ascii=False)}"
        ) from exc


def _json_safe(obj):
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]

    if isinstance(obj, tuple):
        return [_json_safe(v) for v in obj]

    if isinstance(obj, float):
        if not math.isfinite(obj):
            return None
        return obj

    return obj


class AnalyzeCSVView(APIView):
    def post(self, request):
        ser = AnalyzeRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        params = ser.validated_data

        uploaded = request.FILES.getlist("files")
        if not uploaded:
            return Response(
                {"error": "No files uploaded. Use form field name 'files'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = run_analysis(load_uploaded_csvs(uploaded), params)
            request.session["analysis_result"] = result

            return_mode = params.get("return_mode", "summary")

            if return_mode == "export":
                zip_bytes = make_export_zip_bytes(result)
                resp = HttpResponse(zip_bytes, content_type="application/zip")
                resp["Content-Disposition"] = 'attachment; filename="tsproj_results.zip"'
                return resp

            if return_mode == "summary":
                payload = make_summary_payload(
                    result,
                    summary_top_pairs=params.get("summary_top_pairs"),
                )
                payload = _json_safe(payload)
                return Response(payload, status=status.HTTP_200_OK)

            payload = build_entity_response(result, params)
            payload = _json_safe(payload)
            return Response(payload, status=status.HTTP_200_OK)

        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except LookupError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            return Response(
                {"error": f"Unexpected server error: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

def map_fragment(request):
    metric = request.GET.get("metric", "diff_corr")
    significant_only = request.GET.get("significant_only", "0") == "1"
    series_A = request.GET.get("x")
    series_B = request.GET.get("y")

    analysis_result = request.session.get("analysis_result")
    if not analysis_result:
        html = "<div class='muted'>Run an analysis first to display the map.</div>"
        return HttpResponse(html)

    map_rows = build_map_rows(
        analysis_result,
        series_A=series_A,
        series_B=series_B,
    )

    html = build_choropleth_html(
        map_rows,
        metric=metric,
        significant_only=significant_only,
    )
    return HttpResponse(html)


def available_pairs(request):
    analysis_result = request.session.get("analysis_result")
    if not analysis_result:
        return JsonResponse({"pairs": []})

    pairs = extract_available_pairs(analysis_result)
    return JsonResponse({"pairs": pairs})

@ensure_csrf_cookie
def upload_page(request):
    request.session.pop("analysis_result", None)
    request.session.pop("chat_conversation", None)
    request.session.modified = True
    map_html = build_choropleth_html([], metric="diff_corr", significant_only=False)
    return render(
        request,
        "analysis_app/upload_page.html",
        {
            "map_html": map_html,
        },
    )


@require_POST
def chat_with_analysis(request):
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        body = {}

    user_message = (body.get("message") or "").strip()
    selected_entity = (body.get("entity") or "").strip()

    if not user_message:
        return JsonResponse({"error": "Message is required."}, status=400)

    analysis_result = request.session.get("analysis_result")
    if not analysis_result:
        return JsonResponse(
            {"error": "Run an analysis first so the assistant has data to discuss."},
            status=400,
        )

    analysis_context = _build_chat_context_from_result(analysis_result)

    if selected_entity:
        try:
            entity_payload = build_entity_response(
                analysis_result,
                {
                    "entity": selected_entity,
                    "include_prompt": True,
                    "top_pairs": 10,
                    "top_freqs": 5,
                },
            )
            entity_prompt = entity_payload.get("llm_prompt", "")
            analysis_context += (
                f"\n\nCurrent entity selected in the UI: {selected_entity}\n\n"
                f"Entity-specific prompt:\n{entity_prompt}"
            )
        except Exception:
            analysis_context += f"\n\nCurrent entity selected in the UI: {selected_entity}"

    system_message = (
        "You are a strict data analyst. "
        "If correlation is weak (<0.3), clearly say there is no strong relationship. "
        "Do not exaggerate patterns. "
        "Base conclusions strictly on numeric values. "
        "Avoid hallucinating events."
    )

    conversation = request.session.get("chat_conversation", [])
    if not conversation:
        conversation = [
            {"role": "system", "content": system_message},
            {"role": "system", "content": analysis_context},
        ]
    else:
        conversation = [m for m in conversation if m.get("role") != "system"]
        conversation = [
            {"role": "system", "content": system_message},
            {"role": "system", "content": analysis_context},
            *conversation[-6:],
        ]

    conversation.append({"role": "user", "content": user_message})

    try:
        answer = _chat_completion_openrouter(conversation)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)

    stored_conversation = request.session.get("chat_conversation", [])
    stored_conversation.append({"role": "user", "content": user_message})
    stored_conversation.append({"role": "assistant", "content": answer})
    request.session["chat_conversation"] = stored_conversation[-6:]
    request.session.modified = True

    return JsonResponse({"answer": answer})


@require_POST
def reset_chat(request):
    request.session.pop("chat_conversation", None)
    request.session.modified = True
    return JsonResponse({"message": "Chat reset."})


# def _chat_completion_ollama(messages):
#     base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
#     model = os.getenv("OLLAMA_MODEL", "phi3").strip()

#     payload = {
#         "model": model,
#         "messages": messages,
#         "stream": False,
#         "keep_alive": "10m",
#     }

#     req = urlrequest.Request(
#         f"{base_url}/api/chat",
#         data=json.dumps(payload).encode("utf-8"),
#         headers={
#             "Content-Type": "application/json",
#         },
#         method="POST",
#     )

#     try:
#         with urlrequest.urlopen(req, timeout=300) as resp:
#             data = json.loads(resp.read().decode("utf-8"))
#     except error.HTTPError as exc:
#         detail = exc.read().decode("utf-8", errors="replace")
#         raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
#     except error.URLError as exc:
#         raise RuntimeError(
#             f"Could not reach Ollama at {base_url}. Is `ollama serve` running?"
#         ) from exc

#     try:
#         return data["message"]["content"]
#     except (KeyError, TypeError) as exc:
#         raise RuntimeError("Unexpected Ollama response format.") from exc
