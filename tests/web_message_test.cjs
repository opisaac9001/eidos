// Pure DOM-double regression test, not browser automation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
class Node {
  constructor() { this.children = []; this.dataset = {}; this.scrollHeight = 500; this.clientHeight = 100; this.scrollTop = 400; this.hidden = false; this.textContent = ''; }
  set innerHTML(value) { this.html = value; if (value === '<div class="message-author"></div><div class="message-body"></div>') this.children = [{innerHTML: ''}, {textContent: ''}]; }
  get innerHTML() { return this.html || ''; }
  get childElementCount() { return this.children.length; }
  get firstChild() { return this.children[0] || null; }
  get firstElementChild() { return this.children[0]; }
  get lastElementChild() { return this.children.at(-1); }
  get nextSibling() { return this.parent?.children[this.parent.children.indexOf(this)+1] || null; }
  querySelector() { return null; }
  setAttribute(key, value) { this[key] = value; }
  remove() { if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this),1); }
  insertBefore(node, before) { node.remove(); const i = before ? this.children.indexOf(before) : this.children.length; this.children.splice(i,0,node); node.parent = this; }
}
const elements = Object.fromEntries(['messages','send','delivery-note','unread-count','new-messages'].map(id => [id,new Node()]));
const lifeProgress = new Node();
const scope = {
  $: id => elements[id], document: {visibilityState:'visible',createElement:()=>new Node(),querySelectorAll:selector=>selector === '[data-life-progress]' ? [lifeProgress] : []},
  localStorage: {setItem(){}}, readMessageIds: new Set(), pacedReplies:new Map(),
  state:{conversations:[],communication:{}}, currentView:'world', lastMessageSignature:'',
  awaitingLiveReply:false, busy:false, Date, Map, Set, String,
  pacedConversationItem:item=>({item,phase:'complete'}), esc:String, date:()=> 'Jan 8',time:()=> '10:00',
};
vm.createContext(scope);
vm.runInContext(source.slice(source.indexOf('function messageListAtBottom()'),source.indexOf('function renderLifeProgress()')),scope);
vm.runInContext(source.slice(source.indexOf('function renderLifeProgress()'),source.indexOf('document.querySelectorAll("[data-operator-only]")')) + '\nglobalThis.renderLifeProgress = renderLifeProgress;',scope);
vm.runInContext(source.slice(source.indexOf('function renderMessages()'),source.indexOf('function renderEmotionHistory()')) + '\nglobalThis.renderMessages = renderMessages;',scope);
scope.state.attention = {mode:'engrossed',focus_id:'letter',absorption:0.82};
scope.state.volition = {choice:'forming_plan',stated_intention:'Finish the letter before lunch',impulses:[{description:'Finish the letter',strength:0.76,friction:0.14}]};
scope.state.activity_execution = [{title:'Write the letter',schedule_status:'scheduled',window_ended:false,ready:false,blocked_by:null,estimate_confidence:0.6,estimated_seconds:1200,required_seconds:1320,worked_seconds:300,stages:[]}];
scope.renderLifeProgress();
assert.match(lifeProgress.innerHTML,/Attention · engrossed/);
assert.match(lifeProgress.innerHTML,/What reached his attention/);
assert.match(lifeProgress.innerHTML,/Chosen intention: Finish the letter before lunch/);
assert.match(lifeProgress.innerHTML,/Current decision: forming plan/);
assert.match(lifeProgress.innerHTML,/confidence doesn’t guarantee reality/);
scope.state.conversations = [{id:'one',speaker:'pathos',text:'hello',simulated_at:'2026-01-08T10:00:00Z'}];
scope.renderMessages();
assert.equal(elements['unread-count'].textContent,'1');
const original = elements.messages.children[0];
scope.state.conversations.push({id:'two',speaker:'pathos',text:'another thought',simulated_at:'2026-01-08T10:00:00Z'});
scope.renderMessages();
assert.equal(elements.messages.children[0],original, 'Appending must not replace earlier messages');
scope.state.conversations[1].text = 'another thought, a bit longer';
const second = elements.messages.children[1];
scope.renderMessages();
assert.equal(elements.messages.children[1],second,'Paced text must keep its node');
assert.equal(second.lastElementChild.textContent,'another thought, a bit longer');
assert.equal(elements['unread-count'].textContent,'2');
scope.currentView='conversation';
elements.messages.scrollTop=0;
scope.updateUnread(true);
assert.equal(elements['unread-count'].textContent,'2','Reading older messages must not mark new ones read');
assert.equal(elements['new-messages'].hidden,false);
elements.messages.scrollTop=400;
scope.updateUnread(true);
assert.equal(elements['unread-count'].hidden,true);
scope.document.visibilityState='hidden';
scope.state.conversations.push({id:'three',speaker:'pathos',text:'later',simulated_at:'2026-01-08T10:00:00Z'});
scope.renderMessages();
assert.equal(elements['unread-count'].textContent,'1','A hidden tab cannot read a message');
console.log('Message identity, incremental updates, unread and hidden-tab checks passed.');
