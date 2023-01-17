from cli import app
with app.app_context():
  from pybossa.core import user_repo, project_repo
  from pybossa.model.user import User
  from pybossa.model.project import Project
  from test.factories import CategoryFactory

  # Delete existing projects and users.
  for project in project_repo.get_all():
    project_repo.delete(project)
  for user in user_repo.get_all():
    user_repo.delete(user)

  # Create new users.
  user = User(email_addr=u'user@user.com', name=u'user', fullname=u'user', admin=True)
  user.set_password(u'test')
  user_repo.save(user)
with app.app_context():
  from pybossa.core import user_repo
  from pybossa.model.user import User
  user = User(email_addr=u'user2@user.com', name=u'user2', fullname=u'user2', admin=True)
  user.set_password(u'test')
  user_repo.save(user)
with app.app_context():
  from pybossa.core import user_repo
  from pybossa.model.user import User
  user = User(email_addr=u'worker1@worker.com', name=u'worker1',fullname=u'worker1', admin=False)
  user.set_password(u'test')
  user_repo.save(user)

  # Create categories.
  category = CategoryFactory.build(name='One')
  project_repo.delete_category(category)
  project_repo.save_category(category)
