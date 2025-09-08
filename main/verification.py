import subprocess
import json
import logging
import threading
import time
import os
import signal
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

class ExamVerificationSystem:
    def __init__(self):
        self.verification_scripts = {}
        self.active_processes = {}
        self.lock = threading.RLock()  # Changed to RLock for better thread safety
        self.cleanup_thread = None
        self.running = True
        
    def start_cleanup_thread(self):
        """Start a background thread to clean up stuck processes"""
        def cleanup_loop():
            while self.running:
                time.sleep(60)  # Check every minute
                self.cleanup_stuck_processes()
        
        self.cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self.cleanup_thread.start()
    
    def stop_cleanup_thread(self):
        """Stop the cleanup thread"""
        self.running = False
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)
    
    def register_verification_script(self, exam_id, script_path):
        """Register a verification script for a specific exam"""
        with self.lock:
            self.verification_scripts[exam_id] = script_path
    
    def run_verification(self, session_id):
        """Run verification for a specific exam session - non-blocking version"""
        # Import models here to avoid circular imports
        from .models import PracticalExamSession, PracticalExamResult

        try:
            # Check if already running
            with self.lock:
                if session_id in self.active_processes:
                    logger.warning(f"Verification already running for session {session_id}")
                    return {"status": "already_running"}
                
                # Mark as running
                self.active_processes[session_id] = {
                    'start_time': timezone.now(),
                    'process': None,
                    'status': 'starting'
                }
            
            # Start verification in a separate thread to avoid blocking
            verification_thread = threading.Thread(
                target=self._run_verification_thread,
                args=(session_id,),
                daemon=True
            )
            verification_thread.start()
            
            return {"status": "started"}
                
        except Exception as e:
            logger.error(f"Error starting verification for session {session_id}: {str(e)}")
            with self.lock:
                if session_id in self.active_processes:
                    del self.active_processes[session_id]
            return {"status": "error", "message": str(e)}
    
    def _run_verification_thread(self, session_id):
        """Actual verification logic running in a separate thread"""
        from .models import PracticalExamSession, PracticalExamResult

        try:
            with self.lock:
                if session_id not in self.active_processes:
                    return
                
                self.active_processes[session_id]['status'] = 'running'
            
            # Get session and exam
            session = PracticalExamSession.objects.get(id=session_id)
            exam_id = session.exam.id
            
            if exam_id not in self.verification_scripts:
                logger.error(f"No verification script registered for exam ID {exam_id}")
                raise Exception(f"No verification script for exam {exam_id}")
                
            script_path = self.verification_scripts[exam_id]
            
            # Run the verification script with timeout
            with self.lock:
                self.active_processes[session_id]['status'] = 'executing_script'
            
            try:
                # Use Popen with timeout instead of run for better control
                process = subprocess.Popen(
                    ['python', script_path, str(session_id)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    preexec_fn=os.setsid  # Create process group for better cleanup
                )
                
                with self.lock:
                    self.active_processes[session_id]['process'] = process
                    self.active_processes[session_id]['pid'] = process.pid
                
                # Wait for process with timeout
                stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout
                
                if process.returncode == 0:
                    try:
                        verification_data = json.loads(stdout)
                        
                        # Use atomic transaction for database operations
                        with transaction.atomic():
                            # Create or update result
                            result, created = PracticalExamResult.objects.get_or_create(
                                session=session,
                                defaults={
                                    'score': verification_data.get('score', 0),
                                    'total_possible': verification_data.get('total_possible', 100),
                                    'details': verification_data.get('details', {})
                                }
                            )
                            
                            if not created:
                                result.score = verification_data.get('score', 0)
                                result.details = verification_data.get('details', {})
                                result.save()
                            
                            session.is_success = verification_data.get('passed', False)
                            session.verification_output = stdout
                            session.status = 'completed'
                            session.end_time = timezone.now()
                            session.save()
                        
                        # Send email to student
                        self.send_result_email(session, result)
                        
                        with self.lock:
                            if session_id in self.active_processes:
                                self.active_processes[session_id]['status'] = 'completed'
                                del self.active_processes[session_id]
                        
                        logger.info(f"Verification completed successfully for session {session_id}")
                        
                    except json.JSONDecodeError:
                        logger.error(f"Verification script returned invalid JSON: {stdout}")
                        session.verification_output = f"Invalid JSON output: {stdout}\nError: {stderr}"
                        session.status = 'failed'
                        session.save()
                        raise Exception("Invalid JSON output from verification script")
                else:
                    logger.error(f"Verification script failed: {stderr}")
                    session.verification_output = f"Script error: {stderr}"
                    session.status = 'failed'
                    session.save()
                    raise Exception(f"Verification script failed with return code {process.returncode}")
                    
            except subprocess.TimeoutExpired:
                logger.error(f"Verification script timed out for session {session_id}")
                # Kill the entire process group
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass  # Process already terminated
                
                session.verification_output = "Script timed out"
                session.status = 'failed'
                session.save()
                raise Exception("Verification script timed out")
                
        except PracticalExamSession.DoesNotExist:
            logger.error(f"Session {session_id} not found")
            with self.lock:
                if session_id in self.active_processes:
                    del self.active_processes[session_id]
        except Exception as e:
            logger.error(f"Error in verification thread for session {session_id}: {str(e)}")
            with self.lock:
                if session_id in self.active_processes:
                    self.active_processes[session_id]['status'] = 'failed'
                    self.active_processes[session_id]['error'] = str(e)
                    # Don't delete immediately - allow inspection
    
    def send_result_email(self, session, result):
        """Send email to student with exam results"""
        try:
            subject = f"Practical Exam Results: {session.exam.title}"
            message = f"""
            Hello {session.student.get_full_name() or session.student.username},
            
            Your practical exam '{session.exam.title}' has been evaluated.
            
            Score: {result.score}/{result.total_possible}
            Status: {'PASSED' if session.is_success else 'FAILED'}
            
            Detailed results:
            {json.dumps(result.details, indent=2)}
            
            Thank you for completing the exam.
            """
            
            from_email = settings.DEFAULT_FROM_EMAIL
            recipient_list = [session.student.email]
            
            send_mail(subject, message, from_email, recipient_list, fail_silently=False)
            logger.info(f"Result email sent to {session.student.email} for session {session.id}")
            
        except Exception as e:
            logger.error(f"Failed to send result email for session {session.id}: {str(e)}")
    
    def get_verification_status(self, session_id):
        """Get the current status of a verification process"""
        with self.lock:
            if session_id in self.active_processes:
                return self.active_processes[session_id].copy()
            return None
    
    def cleanup_stuck_processes(self):
        """Clean up any verification processes that have been running too long"""
        from .models import PracticalExamSession

        with self.lock:
            current_time = timezone.now()
            sessions_to_cleanup = []
            
            for session_id, process_info in list(self.active_processes.items()):
                if (current_time - process_info['start_time']).total_seconds() > 600:  # 10 minutes
                    sessions_to_cleanup.append(session_id)
            
            for session_id in sessions_to_cleanup:
                process_info = self.active_processes[session_id]
                if 'process' in process_info and process_info['process']:
                    process = process_info['process']
                    if process.poll() is None:
                        logger.warning(f"Killing stuck verification process for session {session_id}")
                        try:
                            # Kill the entire process group
                            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                        except (ProcessLookupError, AttributeError):
                            try:
                                process.kill()
                            except:
                                pass
                
                # Update session status
                try:
                    session = PracticalExamSession.objects.get(id=session_id)
                    session.verification_output = "Verification process was terminated due to timeout"
                    session.status = 'failed'
                    session.save()
                except PracticalExamSession.DoesNotExist:
                    pass
                
                # Remove from active processes
                del self.active_processes[session_id]

# Global instance
verification_system = ExamVerificationSystem()