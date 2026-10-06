from frappe.model.document import Document
from frappe.utils import nowdate


class ITSMKnowledgeArticle(Document):
	def validate(self):
		if self.status == "Published" and not self.published_on:
			self.published_on = nowdate()
