import os
import logging
import urllib
import hashlib
from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.api import memcache
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import template
from google.appengine.datastore import entity_pb

register = webapp.template.create_template_register()

# Adapted and updated from http://www.djangosnippets.org/snippets/772/
# Usage: {% gravatar foo@bar.com %} or {% gravatar foo@bar.com 40 R http://foo.com/bar.jpg %}
def gravatar(email, size=80, rating='g', default_image=''):
    gravatar_url = "http://www.gravatar.com/avatar/"
    gravatar_url += hashlib.md5(email).hexdigest()
    gravatar_url += urllib.urlencode({'s':str(size),
        'r':rating,
        'd':default_image})
    return """<A HREF=http://www.gravatar.com/><img src="%s" alt="gravatar" /></a>""" % gravatar_url

register.simple_tag(gravatar)
# End of gravatar code 

# Both of these functions are courtesy of Nick's blog
# http://blog.notdot.net/2009/9/Efficient-model-memcaching
def serialize_entities(models):
    if models is None:
        return None
    elif isinstance(models, db.Model):
        # Just one instance
        return db.model_to_protobuf(models).Encode()
    else:
        # A list
        return [db.model_to_protobuf(x).Encode() for x in models]

def deserialize_entities(data):
    if data is None:
        return None
    elif isinstance(data, str):
        # Just one instance
        return db.model_from_protobuf(entity_pb.EntityProto(data))
    else:
        return [db.model_from_protobuf(entity_pb.EntityProto(x)) for x in data]
# End of Nick's blog code

def GetMemcacheKey():
    '''The key that i use for memcache entries'''
    return users.get_current_user().email()
    
# Return a runner
def GetRunner():
    '''Returns the current user as a Runner in our system'''
    return Runner.all().filter('user =',users.get_current_user()).get()

def PutRunner():
    '''Adds the current user as a Runner to the datastore'''
    runner = Runner()
    runner.user = users.get_current_user()
    runner.put()
    
def ClearRunCache():
    '''Clears the current runners memcache'''
    memcache.delete(GetMemcacheKey())
            
def GetRuns():
    '''Returns the Runs associated with the currently active Runner.  Looks in memcache first then the datastore'''
    runs = deserialize_entities(memcache.get(GetMemcacheKey()))
    if runs is None:
        runs = Run.all().ancestor(GetRunner())
        if not memcache.set(GetMemcacheKey(), serialize_entities(runs)):
            logging.error("Memcache set failed.")
    return runs

def PutRun(run):
    '''Adds a Run to the system for the currently active Runner. Puts it in the datastore and adds it to memcache'''
    run.put()
    run = Run.all().ancestor(GetRunner())
    if not memcache.set(GetMemcacheKey(), serialize_entities(run)):
        logging.error("Memcache set failed.")
    
class Runner(db.Model):
    '''Model of a Runner in the system'''
    user = db.UserProperty()
    
class Run(db.Model):
    '''Model of a Run in the system.  Runs are ancestors of Runner'''
    name = db.StringProperty()
    distance = db.StringProperty()
    duration = db.StringProperty()
    date = db.DateTimeProperty(auto_now_add=True)

class MainPage(webapp.RequestHandler):
    '''The main page handler.  Reads values for runner, avatar, runs, url and url_linktext and sets them in the template_values Dictionary'''
    def get(self):
        nickname = None
        avatar = None
        runs = None
        runner = None
        
        # Check for current user, populate data if found
        if users.get_current_user():
            runner = GetRunner()
            if runner:
                runs = GetRuns()
            nickname = users.get_current_user().nickname()
            avatar = gravatar(users.get_current_user().email())
            url = users.create_logout_url('/')
            url_linktext = 'Logout'
        else:
            url = users.create_login_url('/')
            url_linktext = 'Login'
            
        template_values = {
            'runner': nickname,
            'avatar': avatar,
            'runs': runs,
            'url': url,
            'url_linktext': url_linktext,
            }

        path = os.path.join(os.path.dirname(__file__), 'index.html')
        self.response.out.write(template.render(path, template_values))
        
class RemoveRunAction(webapp.RequestHandler):
    '''The handler used to remove a Run from the system'''
    def get(self):
         
        # Remove the run when we have a runner parent
        key = self.request.get('key')
        run = Run.get(key)
        run.delete()
        ClearRunCache()

        self.redirect('/')
        
class AddRunAction(webapp.RequestHandler):
    '''The handler used to add a Run to the system.  Also adds the Runner if the Runner is not in the system yet'''
    def post(self):
        
        # Look for the current runner in the datastore first
        runner = GetRunner()
        if not runner:
            PutRunner()
         
        # Save the run when we have a runner parent
        run = Run(parent=GetRunner())
        run.name = self.request.get('name')
        run.distance = self.request.get('distance')
        run.duration = self.request.get('duration')
        PutRun(run)

        self.redirect('/')

application = webapp.WSGIApplication([('/', MainPage),
                                      ('/removeRun', RemoveRunAction),
                                      ('/addRun', AddRunAction)],
                                     debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()