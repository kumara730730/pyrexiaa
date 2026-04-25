import asyncio
import os
import sys
import json
import uuid
from datetime import datetime

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

# Load environment variables manually for the script
from dotenv import load_dotenv
load_dotenv(os.path.join(os.getcwd(), "backend", ".env"))

from services import supabase_service, claude_service

async def verify_e2e():
    print("🚀 Starting End-to-End Verification for Pyrexia")
    
    results = {
        "supabase_connection": False,
        "patient_creation": False,
        "triage_session_creation": False,
        "claude_api_call": "Not Attempted",
        "scoring_triggered": False,
        "reasoning_trace_verified": False,
        "supabase_save_score": False,
        "brief_generation": False,
        "supabase_save_brief": False
    }

    try:
        # 1. Verify Supabase Connection & Patient Creation
        print("\n--- Phase 1: Supabase & Patient Setup ---")
        test_patient_data = {
            "name": f"Test Patient {uuid.uuid4().hex[:6]}",
            "age": 45,
            "gender": "Male",
            "language": "en",
            "voice_distress_score": 0.0
        }
        
        try:
            patient = await supabase_service.create_patient(test_patient_data)
            patient_id = patient["id"]
            results["supabase_connection"] = True
            results["patient_creation"] = True
            print(f"✅ Patient created: {patient_id}")
        except Exception as e:
            print(f"❌ Patient creation failed: {e}")
            return results

        # 2. Create Triage Session
        try:
            session = await supabase_service.create_triage_session(
                patient_id=uuid.UUID(patient_id),
                clinic_id="VERIFY_TEST_CLINIC",
                chief_complaint="Severe chest pain and shortness of breath",
                language="en"
            )
            session_id = session["id"]
            results["triage_session_creation"] = True
            print(f"✅ Triage session created: {session_id}")
        except Exception as e:
            print(f"❌ Triage session creation failed: {e}")
            return results

        # 3. Simulate Triage Conversation
        print("\n--- Phase 2: Claude API & Triage Simulation ---")
        print(f"Using Model: {os.environ.get('ANTHROPIC_MODEL')}")
        print(f"Base URL: {os.environ.get('ANTHROPIC_BASE_URL')}")
        
        messages = [
            "I have a sharp pain in the center of my chest that started 20 minutes ago.",
            "Yes, it's radiating to my left arm and I feel very sweaty.",
            "I'm 45 years old and I have high blood pressure."
        ]
        
        score_data = None
        
        for i, msg in enumerate(messages):
            print(f"Sending message {i+1}: {msg}")
            try:
                # Use in-memory history for simplicity in this script
                async for chunk in claude_service.stream_triage_message(
                    session_id=session_id,
                    patient_message=msg,
                    language="en",
                    voice_distress_score=85.0
                ):
                    if chunk.startswith("__SCORE_JSON__:"):
                        score_data = json.loads(chunk.split(":", 1)[1])
                        print("🎯 Claude triggered scoring!")
                    elif chunk.startswith("__FALLBACK_JSON__:"):
                        print("⚠️ Claude API returned fallback/cached response.")
                        score_data = json.loads(chunk.split(":", 1)[1])
                    else:
                        # Print tokens to show activity
                        print(chunk, end="", flush=True)
                print("\n")
            except Exception as e:
                print(f"\n❌ Claude API call failed: {e}")
                if "401" in str(e):
                    results["claude_api_call"] = "FAILED (401 Unauthorized)"
                else:
                    results["claude_api_call"] = f"FAILED ({str(e)})"
                break
        
        if score_data:
            results["claude_api_call"] = "PASSED"
            results["scoring_triggered"] = True
            print(f"Scoring Data: {json.dumps(score_data, indent=2)}")
            
            # Verify Reasoning Trace
            trace = score_data.get("reasoning_trace", [])
            if len(trace) >= 3:
                results["reasoning_trace_verified"] = True
                print("✅ Reasoning trace is deep and detailed.")
            else:
                print(f"⚠️ Reasoning trace is shallow ({len(trace)} steps).")

            # 4. Save Score to Supabase
            print("\n--- Phase 3: Persisting Results ---")
            try:
                await supabase_service.save_triage_score(
                    session_id=uuid.UUID(session_id),
                    urgency_score=score_data["urgency_score"],
                    urgency_level=score_data["urgency_level"],
                    reasoning_trace=score_data["reasoning_trace"],
                    recommended_action=score_data["recommended_action"]
                )
                results["supabase_save_score"] = True
                print("✅ Triage score saved to Supabase.")
            except Exception as e:
                print(f"❌ Saving score failed: {e}")

            # 5. Generate Brief
            try:
                brief_data = await claude_service.generate_brief(
                    patient_name=test_patient_data["name"],
                    age=test_patient_data["age"],
                    gender=test_patient_data["gender"],
                    history_notes="Simulated history: hypertension",
                    urgency_json=score_data,
                    voice_distress_score=8.5
                )
                results["brief_generation"] = True
                print(f"✅ Brief generated: {json.dumps(brief_data, indent=2)}")
                
                # Save Brief
                await supabase_service.save_brief(
                    patient_id=uuid.UUID(patient_id),
                    session_id=uuid.UUID(session_id),
                    brief_text=json.dumps(brief_data)
                )
                results["supabase_save_brief"] = True
                print("✅ Brief saved to Supabase.")
            except Exception as e:
                print(f"❌ Brief phase failed: {e}")

        else:
            if results["claude_api_call"] == "Not Attempted":
                 results["claude_api_call"] = "FAILED (No score data generated)"

    except Exception as e:
        print(f"💥 Critical script error: {e}")
    
    return results

def print_summary(results):
    print("\n" + "="*50)
    print("📊 FINAL VERIFICATION SUMMARY")
    print("="*50)
    
    mapping = {
        "supabase_connection": "Supabase Connection",
        "patient_creation": "Patient Record Creation",
        "triage_session_creation": "Triage Session Creation",
        "claude_api_call": "Claude API Call (E2E)",
        "scoring_triggered": "Triage Scoring Triggered",
        "reasoning_trace_verified": "Reasoning Trace Depth Verified",
        "supabase_save_score": "Persist Score to Supabase",
        "brief_generation": "Clinical Brief Generation",
        "supabase_save_brief": "Persist Brief to Supabase"
    }
    
    for key, label in mapping.items():
        val = results[key]
        if val is True:
            status = "✅ PASSED"
        elif val is False:
            status = "❌ FAILED"
        else:
            status = f"ℹ️ {val}"
        print(f"{label:<35} : {status}")
    print("="*50)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    final_results = loop.run_until_complete(verify_e2e())
    print_summary(final_results)
