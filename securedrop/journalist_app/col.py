# -*- coding: utf-8 -*-

from flask import (Blueprint, redirect, url_for, render_template, flash,
                   request, abort, send_file, current_app)
from flask_babel import gettext
from sqlalchemy.orm.exc import NoResultFound

from db import db
from models import Submission, Source, Journalist
from journalist_app.forms import ReplyForm, ChangeSourceAssignmentForm
from journalist_app.utils import (make_star_true, make_star_false, get_source,
                                  delete_collection, col_download_unread,
                                  col_download_all, col_star, col_un_star,
                                  col_delete)


def make_blueprint(config):
    view = Blueprint('col', __name__)

    @view.route('/add_star/<filesystem_id>', methods=('POST',))
    def add_star(filesystem_id):
        make_star_true(filesystem_id)
        db.session.commit()
        return redirect(url_for('main.index'))

    @view.route("/remove_star/<filesystem_id>", methods=('POST',))
    def remove_star(filesystem_id):
        make_star_false(filesystem_id)
        db.session.commit()
        return redirect(url_for('main.index'))

    @view.route('/<filesystem_id>')
    def col(filesystem_id):
        reply_form = ReplyForm()
        source = get_source(filesystem_id)
        source.has_key = current_app.crypto_util.getkey(filesystem_id)
        c_form = \
            ChangeSourceAssignmentForm(journalist_uuid=source.assigned_journalist.uuid)
        c_form.journalist_uuid.populate_choices()
        return render_template("col.html",
                               filesystem_id=filesystem_id,
                               source=source,
                               reply_form=reply_form,
                               change_source_assignment_form=c_form)

    @view.route('/delete/<filesystem_id>', methods=('POST',))
    def delete_single(filesystem_id):
        """deleting a single collection from its /col page"""
        source = get_source(filesystem_id)
        delete_collection(filesystem_id)
        flash(gettext("{source_name}'s collection deleted")
              .format(source_name=source.journalist_designation),
              "notification")
        return redirect(url_for('main.index'))

    @view.route('/process', methods=('POST',))
    def process():
        actions = {'download-unread': col_download_unread,
                   'download-all': col_download_all, 'star': col_star,
                   'un-star': col_un_star, 'delete': col_delete}
        if 'cols_selected' not in request.form:
            flash(gettext('No collections selected.'), 'error')
            return redirect(url_for('main.index'))

        # getlist is cgi.FieldStorage.getlist
        cols_selected = request.form.getlist('cols_selected')
        action = request.form['action']

        if action not in actions:
            return abort(500)

        method = actions[action]
        return method(cols_selected)

    @view.route('/<filesystem_id>/<fn>')
    def download_single_file(filesystem_id, fn):
        """Sends a client the contents of a single file, either a submission
        or a journalist reply"""
        if '..' in fn or fn.startswith('/'):
            abort(404)

        # only mark as read when it's a submission (and not a journalist reply)
        if not fn.endswith('reply.gpg'):
            try:
                Submission.query.filter(
                    Submission.filename == fn).one().downloaded = True
                db.session.commit()
            except NoResultFound as e:
                current_app.logger.error(
                    "Could not mark " + fn + " as downloaded: %s" % (e,))

        return send_file(current_app.storage.path(filesystem_id, fn),
                         mimetype="application/pgp-encrypted")

    @view.route('/change-source-assignment/<filesystem_id>', methods=('POST',))
    def change_source_assignment(filesystem_id):
        from flask import current_app, request; current_app.logger.warn(request.form)
        source = get_source(filesystem_id)
        if source is None:
            flash('Source not found.')
            abort(404)

        form = ChangeSourceAssignmentForm()
        form.journalist_uuid.populate_choices()
        if form.validate_on_submit():
            if not form.journalist_uuid.data:
                journalist = None
            else:
                journalist = Journalist.query.filter_by(
                    uuid=form.journalist_uuid.data).one_or_none()
                if journalist is None:
                    abort(404)
                source.assigned_journalist = journalist
            db.session.add(source)
            db.session.commit()
            if journalist:
                flash(gettext('Assigned "{source}" to "{journalist}".')
                      .format(source=source.journalist_designation,
                              journalist=journalist.username),
                      'success')
            else:
                flash(gettext('Unassigned source {source}.')
                      .format(source=source.journalist_designation),
                      'success')
        else:
            flash(gettext('Unable to assign source.'), 'error')

        return redirect(url_for('.col', filesystem_id=source.filesystem_id))

    return view
